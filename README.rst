lazystore
#########

``lazystore`` is a Python package that allows the user to declare objects and
relationships between them without really instantiating them. Instantiation
happens on demand when the user creates a store and asks for some objects.


Install
=======

.. code:: bash

    pip install lazystore


Usage
=====

``lazystore`` has two different types of stores:

1. ``SpecStore``: which will hold "specifications" of objects. Those
   specifications will contain information necessary for later instantiation of
   objects.

2. ``Store``: which will hold instantiated objects. Each instantiated object is
   called an "entry" of the store.

In order to use ``lazystore`` you must use both types of stores. The first to
declare the entries and the second to create the respective instances.

Creating the spec store
-----------------------

After importing ``lazystore``::

    >>> import lazystore

We create the spec store by calling the constructor like below::

    >>> specs = lazystore.SpecStore()

With the spec store in place, we can begin declaring entries::

    >>> specs.Person('john', name='John Doe')
    Person('john')

    >>> specs.Person('jane', name='Jane Doe')
    Person('jane')

On the lines above:

- We are declaring two entries of type ``Person``.

- The id of such entry is passed as the first positional argument (``'john'``).
  The id does not have to be a string: any hashable value is valid. The
  combination of entry type and entry id must be unique across the spec store.

- The rest of the arguments (positional and keyword) belong to the
  specification for this entry (we will see later that those arguments are used
  to instantiate the entry).

You can reference the entry by using the same syntax but using only the id
argument. For example, we are referencing John's entry in the following::

    >>> specs.Person('john')
    Person('john')

Both calls (with full spec or only referencing) return the same type of object,
a ``ValuePromise``. This type implements ``__getattr__``, ``__getitem__``, and
``__call__`` in such a way that you can use the promised value as if it was
using the real object::


    >>> dialog = [
    ...    specs.Person('john').say('Hello! My name is John.'),
    ...    specs.Person('jane').say('Nice to meet you!'),
    ... ]
    >>> dialog
    [Person('john').say('Hello! My name is John.'), Person('jane').say('Nice to meet you!')]

Note that no instantiation has taken place yet::

    >>> type(dialog[0])
    <class 'lazystore._lazystore.ValuePromise'>


Creating resolvers
------------------

In order to know how to instantiate a spec, we need to tell ``lazystore`` what
is the resolver for the respective entry type. The resolver for an entry type
must be a callable that accepts all positional and keyword arguments passed to
the spec store when creating the spec.

The first thing to do is to create a registry, which will hold the resolvers::

    >>> registry = lazystore.Registry()

Then we can define resolvers via ``registry.add_resolver`` or the decorator
``registry.resolver``::

    >>> @registry.resolver('Person')
    ... class Person:
    ...     def __init__(self, store, name):
    ...         print(f'***Instantiating {name}***')
    ...         self.name = name
    ...
    ...     def say(self, line):
    ...         return f'{self.name}: {line}'


Note that the resolver can be any type of callable: it could be a function,
method, class or any other object that implements the ``__call__`` method. In
our example, since we want our generated object to have the method ``say()``,
we defined it as a class.

While this is a very simple example, resolvers can be very complex, they could
make requests for creating database records and perform other necessary
operations. With resolvers, it is possible to encapsulate the "imperative" part
of creating an entry and allow definition of entry specs and relationships
between them in a more declarative way.

Note that the first positional parameter (discarding ``self``) of
``Person.__init__`` is ``store`` which will contain a reference to the store
where the entry will be kept. The remaining parameters are what is expected to
be received from specs created for the entry type "Person".


Creating the store and instantiating entries
--------------------------------------------

Now that we have both ``specs`` and ``registry``, we can create a store with::

    >>> store = lazystore.Store(registry, specs)

Instantiation is done by "resolving" value promises::

    >>> john = store.resolve(specs.Person('john'))
    ***Instantiating John Doe***
    >>> john.say('Hi, there!')
    'John Doe: Hi, there!'

You can use the ``__getattr__`` shortcut as well. The following is equivalent
to the code above::

    >>> john = store.Person('john')
    >>> john.say('Hi, there!')
    'John Doe: Hi, there!'

Note that entries are cached in the store. The same object is returned for the
same combination of entry type and entry id::

    >>> store.Person('john') is john
    True

The method ``resolve()`` can accept different forms of objects. In the
following example, we use the ``dialog`` list created before::

    >>> store.resolve(dialog)
    ***Instantiating Jane Doe***
    ['John Doe: Hello! My name is John.', 'Jane Doe: Nice to meet you!']

(Note that Jane is instantiated only now, when it was needed. John was already
instantiated, so the cached value was returned).

In fact, ``resolve()`` can recurse into lists, tuples and dictionaries. In the
following example we create a dictionary representing a family::

    >>> family_spec = {
    ...     'father': specs.Person('john'),
    ...     'mother': specs.Person('jane'),
    ...     'children': (
    ...         specs.Person('johnny'),
    ...         specs.Person('jannet', name='Jannet Doe'),
    ...     ),
    ... }

We purposefully used only the reference for Johnny to show that the order the
specs are define does not matter. We define it now::

    >>> specs.Person('johnny', name='John Doe Junior')
    Person('johnny')

With all specs ready, we can get the resolved value::

    >>> family = store.resolve(family_spec)
    ***Instantiating John Doe Junior***
    ***Instantiating Jannet Doe***

    >>> family['father'].name
    'John Doe'

    >>> family['mother'].name
    'Jane Doe'

    >>> [c.name for c in family['children']]
    ['John Doe Junior', 'Jannet Doe']
