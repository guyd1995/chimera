from typing import Any, Union, List
import re
from . import _inject_new_params, _match_string_to_regex
from torch import nn
from functools import partial
from copy import deepcopy


# VERY EXPERIMENTAL!
def _subclass_instance(instance: Any, new_attrs: dict):
    def do_nothing(*args, **kwargs):
        pass

    def call_super(*args, **kwargs):
        return super().__init__(*args, **kwargs)

    Subclass = type('Subclass', (instance.__class__,), {'__init__': do_nothing})

    new_instance = Subclass()
    for attr in instance.__dict__.keys():  # dir(instance):
        if attr in ['__weakref__', '__class__', *new_attrs.keys()]:
            continue
        new_instance.__dict__[attr] = instance.__dict__[attr]
    #         setattr(new_instance, attr, getattr(instance, attr))

    Subclass.__init__ = call_super

    for attr, val in new_attrs.items():
        setattr(Subclass, attr, val)

    return new_instance


def _experimental_override_parameters(base_model: nn.Module, replacement_model: nn.Module, pass_idx: bool = True,
                                      match_string: Union[List[str], str, None] = None, clone: bool = True,
                                      verbose: bool = False):
    if isinstance(match_string, str):
        match_string = [match_string]
    patterns = [_match_string_to_regex(raw_pattern) for raw_pattern in match_string]
    replaced_params = [name for name, _ in base_model.named_parameters()
                       if any(re.search(pattern, name) for pattern in patterns)]

    if clone:
        base_model = deepcopy(base_model)

    for idx, name in enumerate(replaced_params):
        if verbose:
            print(f"injection to parameter {name}")
        old_param = base_model.get_parameter(name)
        submodule_name, param_base_name = name.rsplit('.', 1)
        submodule = base_model.get_submodule(submodule_name)
        submodule.register_parameter(f'_chimera_old_{param_base_name}', old_param)
        _replace_fn = partial(replacement_model.forward, old_param)
        if pass_idx:
            _replace_fn = partial(_replace_fn, idx=idx)
        assert (param_base_name in submodule._parameters) and (submodule._parameters[param_base_name] is old_param)
        submodule.register_parameter(param_base_name, None)
        # TODO: make it work for integer param_base_name & submodule_base_name
        new_submodule = _subclass_instance(submodule, {param_base_name: property(_replace_fn)})
        if submodule_name == '':
            base_model = new_submodule
        else:
            parent_submodule_name, submodule_base_name = submodule_name.rsplit('.', 1)
            parent_submodule = base_model.get_submodule(parent_submodule_name)
            parent_submodule.__dict__[submodule_base_name] = new_submodule
    _inject_new_params(base_model, replacement_model)
    return base_model