# PE4 - Battleship++

## Documentation

To build the documentation navigate to `/docs` and run:

1. `sphinx-apidoc -f -o . ..` to scan source files
1. `make html` to build html documentation

If python2 is your main python version you need to install `enum34` (`pip install enum34`).

## Deployment

### Client

#### Dependencies

* Python 3
* Qt5
* PyQt5
* Sphinx with autodoc to build the documentation

#### Run

Navigate to `/client` and run `python3 main.py`.
