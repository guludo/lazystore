import sys
import re

import pytest

import lazystore
from lazystore import _lazystore


def test_plain_object_repr_and_str():
    o = lazystore.PlainObject(a=1, b=['list', 'of', 'things'])
    assert repr(o) == "PlainObject(a=1, b=['list', 'of', 'things'])"
    assert repr(o) == str(o)


def test_plain_object_equality():
    assert lazystore.PlainObject(a=1, b=2) == lazystore.PlainObject(a=1, b=2)


def test_plain_object_repr_recursive():
    o = lazystore.PlainObject(a=1)
    o.b = o
    assert repr(o) == 'PlainObject(a=1, b=...)'


def test_spec_store_invalid_attr():
    specs = lazystore.SpecStore()
    expected_msg = re.escape(
        'Helpers for entry types starting with "_" can not be used via '
        'attribute access. Use spec_helper() instead.'
    )
    with pytest.raises(AttributeError, match=expected_msg):
        specs._Person


def test_spec_store_attr():
    specs = lazystore.SpecStore()
    helper = specs.Person
    other_helper = specs.spec_helper('Person')
    assert type(helper) is type(other_helper)
    assert helper.__dict__ == other_helper.__dict__


def test_spec_store_duplicate_spec():
    specs = lazystore.SpecStore()
    specs.Person(1, name='John')
    expected_msg = re.escape(
        'Duplicate specs detected for Person(1):\n'
        "First: Spec(entry_type='Person', entry_id=1, args=(), "
        "kwargs={'name': 'John'})\n"
        "Second: Spec(entry_type='Person', entry_id=1, args=(), "
        "kwargs={'name': 'Jack'})"
    )
    with pytest.raises(RuntimeError, match=expected_msg):
      specs.Person(1, name='Jack')


def test_spec_store_required_entry_id():
    specs = lazystore.SpecStore()
    expected_msg = re.escape(
        'Entry id is required when no arguments are passed to Person()'
    )
    with pytest.raises(ValueError, match=expected_msg):
        specs.Person()


def test_spec_store_auto_id():
    specs = lazystore.SpecStore()
    john = specs.Person(name='John')
    jack = specs.Person(name='Jack')
    assert isinstance(specs.get(john).entry_id, _lazystore.AutoId)
    assert isinstance(specs.get(jack).entry_id, _lazystore.AutoId)
    assert specs.get(john).entry_id != specs.get(jack).entry_id

    assert repr(john) == 'Person(AutoId())'
    assert repr(jack) == 'Person(AutoId())'
    assert repr(specs.get(john).entry_id) == str(specs.get(john).entry_id)


def test_spec_store_non_existing_ref():
    specs = lazystore.SpecStore()
    ref = lazystore.Spec('Foo', 1, tuple(), {}).ref()
    expected_msg = re.escape('No spec found for Foo(1)')
    with pytest.raises(KeyError, match=expected_msg):
        specs.get(ref)


def test_spec_store_contains_ref():
    specs = lazystore.SpecStore()
    spec = lazystore.Spec('Foo', 1, tuple(), {})
    ref = spec.ref()
    assert (ref in specs) is False
    specs.add(spec)
    assert (ref in specs) is True


def test_spec_store_contains_value_promise():
    specs = lazystore.SpecStore()
    promise = specs.Person(1, name='John')
    assert (promise in specs) is True
    another_spec_store = lazystore.SpecStore()
    assert (promise in another_spec_store) is False


def test_spec_store_get_from_value_promise():
    specs = lazystore.SpecStore()
    promise = specs.Person(1, name='John')
    ref = promise._payload
    assert specs.get(ref) is specs.get(promise)


def test_spec_store_len():
    specs = lazystore.SpecStore()
    assert len(specs) == 0
    specs.Person(1, name='John')
    assert len(specs) == 1
    specs.Person(2, name='Jack')
    assert len(specs) == 2


def test_spec_store_iter():
    specs = lazystore.SpecStore()
    promises = [specs.Person(1, name='John'), specs.Person(2, name='Jack')]
    expected = [specs.get(p).ref() for p in promises]
    assert expected == list(specs)


def test_store_with_spec_store_omitted():
    store = lazystore.Store()
    assert isinstance(store.specs, lazystore.SpecStore)
    assert len(store.specs) == 0


def test_general_resolver():
    specs = lazystore.SpecStore()
    registry = lazystore.Registry()
    store = lazystore.Store(registry, specs)

    class Dog(lazystore.PlainObject):
        pass

    class Cat(lazystore.PlainObject):
        pass

    @registry.resolver
    def create_entry(store, spec, **kw):
        print(spec)
        if spec.entry_type == 'Dog':
            return Dog(**kw)
        if spec.entry_type == 'Cat':
            return Cat(**kw)
        return NotImplemented

    specs.Dog('dog-1', name='Max')
    specs.Cat('cat-1', name='Garfield')

    assert store.Dog('dog-1') == Dog(name='Max')
    assert store.Cat('cat-1') == Cat(name='Garfield')


def test_multiple_general_resolvers():
    specs = lazystore.SpecStore()
    registry = lazystore.Registry()
    store = lazystore.Store(registry, specs)

    class Dog(lazystore.PlainObject):
        def __init__(self, name):
            super().__init__(name=name)

    class Cat(lazystore.PlainObject):
        def __init__(self, name):
            super().__init__(name=name)

    def generate_sequence(spec, args):
        if spec.entry_type.startswith('Dog'):
            constructor = Dog
        elif spec.entry_type.startswith('Cat'):
            constructor = Cat
        else:
            raise ValueError()
        for arg in args:
            yield constructor(name=arg)

    @registry.resolver
    def create_list(store, spec, *args):
        if spec.entry_type.endswith('List'):
            seq = generate_sequence(spec, args)
            try:
                first = next(seq)
            except ValueError:
                return NotImplemented
            return [first, *seq]
        return NotImplemented

    @registry.resolver
    def create_tuple(store, spec, *args):
        if spec.entry_type.endswith('Tuple'):
            seq = generate_sequence(spec, args)
            try:
                first = next(seq)
            except ValueError:
                return NotImplemented
            return (first, *seq)
        return NotImplemented

    actual = store.resolve(specs.CatList('catlist', 'Cat 1', 'Cat 2'))
    expected = [Cat('Cat 1'), Cat('Cat 2')]
    assert actual == expected

    actual = store.resolve(specs.CatTuple('cattuple', 'Cat A', 'Cat B'))
    expected = (Cat('Cat A'), Cat('Cat B'))
    assert actual == expected

    actual = store.resolve(specs.DogList('doglist', 'Dog 1', 'Dog 2'))
    expected = [Dog('Dog 1'), Dog('Dog 2')]
    assert actual == expected

    actual = store.resolve(specs.DogTuple('dogtuple', 'Dog A', 'Dog B'))
    expected = (Dog('Dog A'), Dog('Dog B'))
    assert actual == expected

    expected_msg = re.escape(
        "No resolver found for DogSet('dogset')."
    )
    with pytest.raises(RuntimeError, match=expected_msg):
        store.resolve(specs.DogSet('dogset', 'Dog A', 'Dog B'))

    expected_msg = re.escape(
        "No resolver found for BirdList('birdlist')."
    )
    with pytest.raises(RuntimeError, match=expected_msg):
        store.resolve(specs.BirdList('birdlist', 'Bird 1', 'Bird 2'))


def test_store_set_resolved():
    store = lazystore.Store()

    store.set_resolved(store.specs.Foo(1), 1)
    assert store.Foo(1) == 1

    expected_msg = re.escape(
        "There is value for Foo(1) already."
    )
    with pytest.raises(RuntimeError, match=expected_msg):
        store.set_resolved(store.specs.Foo(1), 2)
    assert store.Foo(1) == 1

    store.set_resolved(store.specs.Foo(1), 2, overwrite=True)
    assert store.Foo(1) == 2


def test_store_is_resolved_value_promise():
    store = lazystore.Store()
    assert store.is_resolved(store.specs.Foo(1)) is False
    store.set_resolved(store.specs.Foo(1), 1)
    assert store.is_resolved(store.specs.Foo(1)) is True


def test_store_resolve_all():
    registry = lazystore.Registry()
    store = lazystore.Store(registry)

    @registry.resolver
    def create_any(store, specs, *k):
        return (specs.entry_type, specs.entry_id, *k)

    store.specs.Foo(1, 'First foo')
    store.specs.Foo(2, 'Second foo')
    store.specs.Bar(1, 'First bar')
    store.specs.Bar(2, 'Second bar')

    actual = store.resolve_all()
    expected = {
        store.specs.Foo.ref(1): ('Foo', 1, 'First foo'),
        store.specs.Foo.ref(2): ('Foo', 2, 'Second foo'),
        store.specs.Bar.ref(1): ('Bar', 1, 'First bar'),
        store.specs.Bar.ref(2): ('Bar', 2, 'Second bar'),
    }
    assert actual == expected


def test_value_promise_attribute():
    store = lazystore.Store()
    p = _lazystore.ValuePromise(lazystore.PlainObject(a=1, b=2))
    assert store.resolve(p.a) == 1
    assert store.resolve(p.b) == 2


def test_value_promise_invalid_attribute():
    specs = lazystore.SpecStore()
    foo = specs.Foo(1)
    expected_msg = re.escape(
        "Names passed to ValuePromise.__getattr__ can not start with '_'. "
        "Got: '_bar'"
    )
    with pytest.raises(AttributeError, match=expected_msg):
        foo._bar


def test_value_promise_subscription():
    store = lazystore.Store()
    p = _lazystore.ValuePromise([1, 2, 3])
    assert store.resolve(p[1]) == 2
    assert store.resolve(p[2]) == 3


def test_value_promise_call():
    store = lazystore.Store()
    p = _lazystore.ValuePromise('hello world')
    assert store.resolve(p.upper()) == 'HELLO WORLD'
    assert store.resolve(p.startswith('hi')) is False
    assert store.resolve(p.startswith('hello')) is True


def test_value_promise_str_equals_repr():
    specs = lazystore.SpecStore()
    foo = specs.Foo(1)
    assert str(foo) == repr(foo)


def test_value_promise_repr():
    specs = lazystore.SpecStore()
    foo = specs.Foo(1)
    actual = repr(foo(foo.x, foo.y, foo[1], foo[foo.x[foo.z(45)]]))
    expected = 'Foo(1)(Foo(1).x, Foo(1).y, Foo(1)[1], Foo(1)[Foo(1).x[Foo(1).z(45)]])'
    assert actual == expected


def test_value_promise_callable_with_promises():
    store = lazystore.Store()
    a_promise = _lazystore.ValuePromise(1)
    b_promise = _lazystore.ValuePromise(2)
    assert store.resolve(lambda a=a_promise, b=b_promise: a + b) == 3
    assert store.resolve(lambda a=90, b=b_promise: a + b) == 92


def test_value_promise_callable_without_promises():
    store = lazystore.Store()
    f = store.resolve(lambda a, b: a + b)
    assert callable(f) is True
    assert f(1, 2) == 3


def test_value_promise_invalid_callable():
    store = lazystore.Store()
    b_promise = _lazystore.ValuePromise(2)
    expected_msg = re.escape(
        'All parameters of a "callable promise" must have default values '
        'defined.'
    )
    with pytest.raises(RuntimeError, match=expected_msg):
        store.resolve(lambda a, b=b_promise: a + b)


def test_value_promise_circular_dependency():
    specs = lazystore.SpecStore()
    registry = lazystore.Registry()
    store = lazystore.Store(registry, specs)

    specs.A(1, a=specs.B(1, b=specs.C(2, c=specs.A(1))))
    expected_msg = re.escape(
        'Cyclic dependency detected: A(1) -> B(1) -> C(2) -> A(1)'
    )
    with pytest.raises(RuntimeError, match=expected_msg):
        store.A(1)
