# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from __future__ import annotations

import inspect
import logging
import typing as ty


_logger = logging.getLogger(__name__)


class Spec(ty.NamedTuple):
    """
    A Spec object represents a specification of an object to be instantiated
    by a Store.
    """
    entry_type: str
    entry_id: ty.Hashable
    args: ty.Tuple[ty.Any, ...]
    kwargs: ty.Dict[str, ty.Any]

    def ref(self) -> SpecRef:
        return SpecRef(self.entry_type, self.entry_id)


class SpecRef(ty.NamedTuple):
    """
    A SpecRef represents a reference to a specification. A SpecStore uses
    SpecRef instances to map added specs. Two references to two different specs
    are evaluated as equal if both specs have the same entry type and id.
    """
    entry_type: str
    entry_id: ty.Hashable

    def __str__(self) -> str:
        return repr(self)

    def __repr__(self) -> str:
        return f'{self.entry_type}({self.entry_id!r})'


class SpecStore:
    """
    A SpecStore is where specification of entries are managed.
    """
    def __init__(self) -> None:
        self.__specs: ty.Dict[SpecRef, Spec] = {}

    def __getattr__(self, entry_type: str) -> SpecHelper:
        if entry_type.startswith('_'):
            raise AttributeError(
                'Helpers for entry types starting with "_" can not be used '
                'via attribute access. Use spec_helper() instead.'
            )
        return self.spec_helper(entry_type)

    def add(self, spec: Spec) -> SpecRef:
        ref = spec.ref()
        if ref in self.__specs:
            raise RuntimeError(
                f'Duplicate specs detected for {ref}:\n'
                f'First: {self.__specs[ref]}\n'
                f'Second: {spec}'
            )
        self.__specs[ref] = spec
        return ref

    def get(self, ref: ty.Union[SpecRef, ValuePromise]) -> Spec:
        if isinstance(ref, ValuePromise):
            ref = ty.cast(SpecRef, ref._payload)
        try:
            return self.__specs[ref]
        except KeyError:
            raise KeyError(f'No spec found for {ref}')

    def spec_helper(self, entry_type: str) -> SpecHelper:
        return SpecHelper(self, entry_type)

    def __contains__(self, ref: ty.Union[SpecRef, ValuePromise]) -> bool:
        if isinstance(ref, ValuePromise):
            ref = ref._payload
        return ref in self.__specs

    def __len__(self) -> int:
        return len(self.__specs)

    def __iter__(self) -> ty.Iterator[SpecRef]:
        return iter(self.__specs)


class ResolverConf(ty.NamedTuple):
    """
    Named tuple stored internally by Registry instances.
    """
    fn: ty.Callable[..., ty.Any]
    with_store: bool
    with_spec: bool


CallableT = ty.TypeVar('CallableT', bound=ty.Callable[..., ty.Any])


class Registry:
    """
    A Registry object is where users can register resolvers for entry types.
    """
    def __init__(self) -> None:
        self.__general_resolvers: ty.List[ResolverConf] = []
        self.__entry_type_resolvers: ty.Dict[str, ResolverConf] = {}

    @ty.overload
    def resolver(self, arg: CallableT) -> CallableT:
        ... # pragma: no cover
    @ty.overload
    def resolver(self,
                 arg: ty.Optional[str],
                 **kwargs: ty.Any,
                 ) -> ty.Callable[[CallableT], CallableT]:
        ... # pragma: no cover
    def resolver(self,
                 arg: ty.Union[None, str, CallableT],
                 **kwargs: ty.Any,
                 ) -> ty.Union[CallableT, ty.Callable[[CallableT], CallableT]]:
        if callable(arg):
            kwargs.setdefault('with_spec', True)
            self.add_resolver(arg, **kwargs)
            return arg

        def decorator(fn: CallableT) -> CallableT:
            self.add_resolver(fn, ty.cast(ty.Optional[str], arg), **kwargs)
            return fn
        return decorator

    def add_resolver(self,
                     resolver: ty.Callable[..., ty.Any],
                     entry_type: ty.Optional[str] = None,
                     with_store: bool = True,
                     with_spec: bool = False,
                     ) -> None:
        rconf = ResolverConf(resolver, with_store, with_spec)
        if entry_type is None:
            self.__general_resolvers.append(rconf)
        else:
            self.__entry_type_resolvers[entry_type] = rconf

    def resolve_spec(self, store: Store, spec: Spec) -> ty.Any:
        def call_resolver(rconf: ResolverConf) -> ty.Any:
            args = spec.args
            if rconf.with_spec:
                args = (spec,) + args
            if rconf.with_store:
                args = (store,) + args
            return rconf.fn(*args, **spec.kwargs)

        if spec.entry_type in self.__entry_type_resolvers:
            return call_resolver(self.__entry_type_resolvers[spec.entry_type])

        for r in self.__general_resolvers:
            resolved = call_resolver(r)
            if resolved is NotImplemented:
                continue
            break
        else:
            return NotImplemented
        return resolved


class Store:
    """
    A Store is responsible for instantiating and managing entries that were
    previously specified in a SpecStore.
    """
    def __init__(self,
                 registries: ty.Union[Registry,
                                      ty.Iterable[Registry]] = [],
                 specs: ty.Optional[SpecStore] = None,
                 ctx: ty.Any = None,
                 ):
        self.__entries: ty.Dict[SpecRef, ty.Any] = {}

        if specs is None:
            self.specs = SpecStore()
        else:
            self.specs = specs

        if isinstance(registries, Registry):
            self.registries = [registries]
        else:
            self.registries = list(registries)

        self.ctx = ctx if ctx is not None else PlainObject()

    def _resolve_spec(self, spec: Spec) -> ty.Any:
        for registry in self.registries:
            resolved = registry.resolve_spec(self, spec)
            if resolved is NotImplemented:
                continue
            return resolved
        raise RuntimeError(
            f'No resolver found for {spec.ref()}.'
        )

    def __getattr__(self, entry_type: str) -> ty.Callable[[ty.Hashable],
                                                          ty.Any]:
        def resolve_entry(entry_id: ty.Hashable) -> ty.Any:
            ref = SpecRef(entry_type, entry_id)
            return self.resolve(ref)
        return resolve_entry

    def resolve(self, value: ty.Any) -> ty.Any:
        if isinstance(value, SpecRef) and self.is_resolved(value):
            return self.__entries[value]
        return ValueResolver(self, value).resolve()

    def set_resolved(self,
                     ref: ty.Union[SpecRef, ValuePromise],
                     value: ty.Any,
                     overwrite: bool = False) -> None:
        if isinstance(ref, ValuePromise):
            ref = ty.cast(SpecRef, ref._payload)
        if self.is_resolved(ref) and not overwrite:
            raise RuntimeError(
                f'There is value for {ref} already.'
            )
        self.__entries[ref] = value

    def is_resolved(self, ref: ty.Union[SpecRef, ValuePromise]) -> bool:
        if isinstance(ref, ValuePromise):
            ref = ref._payload
        return ref in self.__entries

    def resolve_all(self) -> ty.Dict[SpecRef, ty.Any]:
        return {
            ref: self.resolve(ref)
            for ref in self.specs
        }


class SpecHelper:
    """
    A SpecHelper provides utility functions to create or reference specs for a
    specific SpecStore.

    Instances of this class are returned by calling ``SpecStore.spec_helper()``
    or using an entry type name as attribute of a SpecStore (i.e., by calling
    ``SpecStore.__getattr__``).
    """
    def __init__(self, specs: SpecStore, entry_type: str):
        self.__specs = specs
        self.__entry_type = entry_type

    def __call__(self,
                 _entry_id: ty.Optional[ty.Hashable] = None,
                 *args: ty.Any,
                 **kwargs: ty.Any,
                 ) -> ValuePromise:
        if len(args) + len(kwargs) == 0:
            if _entry_id is None:
                raise ValueError(
                    'Entry id is required when no arguments are passed '
                    f'to {self.__entry_type}()'
                )
            return self.promise(_entry_id)

        if _entry_id is None:
            _entry_id = AutoId()

        return self.new_spec(_entry_id, args, kwargs)

    def new_spec(self,
                 entry_id: ty.Hashable,
                 args: ty.Tuple[ty.Any, ...],
                 kwargs: ty.Dict[str, ty.Any],
                 ) -> ValuePromise:
        spec = Spec(self.__entry_type, entry_id, args, kwargs)
        self.__specs.add(spec)
        return self.promise(entry_id)

    def ref(self, entry_id: ty.Hashable) -> SpecRef:
        return SpecRef(self.__entry_type, entry_id)

    def promise(self, entry_id: ty.Hashable) -> ValuePromise:
        return ValuePromise(self.ref(entry_id))


# TODO: Use this instead when typing_extensions is added as dependency.
# ValuePromiseOperator = ty.Literal[
#     'attribute',
#     'call',
#     'subscription',
#     'value',
# ]
ValuePromiseOperator = str


class ValuePromise:
    """
    A ValuePromise is an object that will be resolved later to the value it
    represents.
    """
    def __init__(self,
                 payload: ty.Any,
                 op: ValuePromiseOperator = 'value',
                 ):
        self._payload = payload
        self._op = op

    def __getattr__(self, name: ty.Any) -> ValuePromise:
        if name.startswith('_'):
            raise AttributeError(
                'Names passed to ValuePromise.__getattr__ can not start '
                f"with '_'. Got: {name!r}"
            )
        return ValuePromise((self, name), 'attribute')

    def __getitem__(self, key: ty.Any) -> ValuePromise:
        return ValuePromise((self, key), 'subscription')

    def __call__(self, *k: ty.Any, **kw: ty.Any) -> ValuePromise:
        return ValuePromise((self, k, kw), 'call')

    def __str__(self) -> str:
        return repr(self)

    def __repr__(self) -> str:
        if self._op == 'attribute':
            obj, name = self._payload
            return f'{obj!r}.{name}'
        elif self._op == 'subscription':
            obj, key = self._payload
            return f'{obj!r}[{key!r}]'
        elif self._op == 'call':
            fn, args, kwargs = self._payload
            full_args_str = ', '.join((
                *(repr(v) for v in args),
                *(f'{k}={v!r}' for k, v in kwargs.items()),
            ))
            return f'{fn!r}({full_args_str})'
        elif self._op == 'value':
            return repr(self._payload)
        raise RuntimeError(f'Unhandled operator {self._op}. This is a bug.') # pragma: no cover


class ValueResolver:
    """
    Class responsible for implementing the logic necessary for resolving
    values.
    """
    def __init__(self, store: Store, value: ty.Any):
        self.__store = store
        self.__root = value
        self.__spec_ref_stack: ty.List[SpecRef] = []
        self.__cache: ty.Dict[ty.Hashable, ty.Any] = {}

    def resolve(self) -> ty.Any:
        return self.__resolve_value(self.__root)

    def __resolve_value(self, value: ty.Any) -> ty.Any:
        if id(value) in self.__cache:
            return self.__cache[id(value)]

        if isinstance(value, ValuePromise):
            resolved = self.__resolve_promise(value)
        elif isinstance(value, SpecRef):
            resolved = self.__resolve_spec_ref(value)
        elif isinstance(value, dict):
            resolved = self.__resolve_dict(value)
        elif isinstance(value, tuple):
            resolved = self.__resolve_tuple(value)
        elif isinstance(value, list):
            resolved = self.__resolve_list(value)
        elif self.__is_callable_with_promises(value):
            resolved = self.__resolve_callable_with_promises(value)
        else:
            resolved = value

        self.__cache[id(value)] = resolved
        return resolved

    def __resolve_dict(self,
                       value: ty.Dict[ty.Any, ty.Any],
                       ) -> ty.Dict[ty.Any, ty.Any]:
        resolved = {}
        for k, v in value.items():
            resolved_k = self.__resolve_value(k)
            resolved_v = self.__resolve_value(v)
            resolved[resolved_k] = resolved_v
        return resolved

    def __resolve_tuple(self,
                        value: ty.Tuple[ty.Any, ...],
                        ) -> ty.Tuple[ty.Any, ...]:
        return tuple(self.__resolve_value(item) for item in value)

    def __resolve_list(self,
                       value: ty.List[ty.Any],
                       ) -> ty.List[ty.Any]:
        return list(self.__resolve_value(item) for item in value)

    def __is_callable_with_promises(self, value: ty.Any) -> bool:
        if not callable(value):
            return False
        sig = inspect.signature(value)
        for param in sig.parameters.values():
            if isinstance(param.default, ValuePromise):
                return True
        return False

    def __resolve_callable_with_promises(self,
                                         value: ty.Callable[..., ty.Any],
                                         ) -> ty.Any:
        sig = inspect.signature(value)
        bound = sig.bind_partial()
        bound.apply_defaults()
        new_sig = inspect.signature(value)
        for name, param in sig.parameters.items():
            if param.default is param.empty:
                raise RuntimeError(
                    'All parameters of a "callable promise" must have default '
                    'values defined.'
                )
            bound.arguments[name] = self.__resolve_value(param.default)
        return value(*bound.args, **bound.kwargs)

    def __resolve_spec_ref(self, ref: SpecRef) -> ty.Any:
            _logger.debug(f'Resolving {ref}')
            if self.__store.is_resolved(ref):
                resolved = self.__store.resolve(ref)
                _logger.debug(f'{ref} resolved from cache to {resolved!r}')
                return resolved

            _logger.debug(f'Resolving {ref}')
            if ref in self.__spec_ref_stack:
                chain_str = ' -> '.join(
                    str(ref) for ref in (self.__spec_ref_stack + [ref])
                )
                raise RuntimeError(
                    f'Cyclic dependency detected: {chain_str}'
                )

            self.__spec_ref_stack.append(ref)
            spec = self.__store.specs.get(ref)
            args = self.__resolve_value(spec.args)
            kwargs = self.__resolve_value(spec.kwargs)
            spec = spec._replace(args=args, kwargs=kwargs)
            resolved = self.__store._resolve_spec(spec)
            _logger.debug(f'{ref} resolved to {resolved!r}')
            self.__store.set_resolved(ref, resolved)
            self.__spec_ref_stack.pop()
            return resolved

    def __resolve_promise(self, p: ValuePromise) -> ty.Any:
        if p._op == 'attribute':
            obj, name = self.__resolve_value(p._payload)
            resolved = getattr(obj, name)
        elif p._op == 'call':
            fn, args, kwargs = self.__resolve_value(p._payload)
            resolved = fn(*args, **kwargs)
        elif p._op == 'subscription':
            obj, key = self.__resolve_value(p._payload)
            resolved = obj[key]
        elif p._op == 'value':
            resolved = self.__resolve_value(p._payload)
        else:
            raise RuntimeError( # pragma: no cover
                f'Unhandled promise operator {p._op}. This is a bug.'
            )
        return resolved


class AutoId:
    __slots__: ty.List[str] = []

    def __str__(self) -> str:
        return 'AutoId()'

    def __repr__(self) -> str:
        return 'AutoId()'


class PlainObject:
    """
    This class is used to create the default context of a store if none is
    passed. This can also be used by users to create objects for general use
    (e.g. as a returned value of a resolver).
    """
    def __init__(self, **kw: ty.Any):
        for k, v in kw.items():
            setattr(self, k, v)

    def __eq__(self, other: ty.Any) -> bool:
        return type(other) == type(self) and self.__dict__ == other.__dict__

    def __str__(self) -> str:
        return repr(self)

    def __repr__(self) -> str:
        try:
            if self.__repr_running: # type: ignore
                return '...'
        except AttributeError:
            pass

        dict_copy = dict(self.__dict__)
        self.__repr_running = True
        r = (
            f'{type(self).__name__}('
            + ', '.join(f'{k}={v!r}' for k, v in dict_copy.items())
            + ')'
        )
        del self.__repr_running
        return r
