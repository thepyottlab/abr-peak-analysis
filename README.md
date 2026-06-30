![splash](Source/splash.png)

This is the EPL-maintained version of the program originally written by Brad Buran.

[Help](https://EPL-Engineering.github.io/abr-peak-analysis/)

[Changelog](CHANGELOG.md)

Runtime environment:
```bash
conda create -n abr python=3.9.12 pip
conda activate abr
python -m pip install -r requirements.txt
python Source/notebook.py
```

Developer build tool:
```bash
python -m pip install pyinstaller
```

Notes: numpy v2.0.1 has bugs that break bundled apps without a console, e.g.:
```
  File "numpy\f2py\cfuncs.py", line 19, in <module>
    errmess = sys.stderr.write
AttributeError: 'NoneType' object has no attribute 'write'
```

See [here](https://github.com/numpy/numpy/issues/26862)
