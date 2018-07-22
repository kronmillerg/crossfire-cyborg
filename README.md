# CrossFire Cyborg

A collection of scripts and scripting infrastructure for use with the game
[CrossFire](http://crossfire.real-time.com/).

Still somewhat under construction; don't mind the exposed ducts.

Also, be aware that the infrastructure behind these scripts has grown somewhat
in scope since my earlier attempts. In places it probably more resembles an
attempt at writing a Python client than it does a library for scripting.

## Getting started

Main entry-point scripts are in the `main/` directory. To run one of them, use

```
script ./run script-name <args>
```

where `script-name` does not include the `.py` extension. For example:

```
script ./run monk_id
```

There are also some test programs in `test/`, which are useful when developing
but don't really provide any in-game value. If you want to run one of them, use

```
script ./runtest script-name <args>
```

