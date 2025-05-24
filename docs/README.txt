# Generate Docs

Sphinx is used to build the website.

```Shell
sphinx-build -b html ./docs ./docs/_build/html
# or in /docs
sphinx-build -b html ./ ./_build/html
```

Viewing the document in a browser:

```Shell
cd ./_build/html
python -m http.server
```

In browser go to [localhost:8000]() to view the documentation.
