export PIPENV_VERBOSITY=-1

# get version string
version  = $(shell cat walrus.py | grep "^__version__" | sed "s/__version__ = '\(.*\)'/\1/")

after: git-after
clean: pypi-clean
pipenv: pipenv-update
maintainer: update-maintainer

dist: pipenv test pypi setup github formula maintainer after
github: git-upload git-release
pypi: pypi-dist pypi-upload
setup: setup-version setup-manual

coverage:
	pipenv run coverage run tests/test.py
	pipenv run coverage html
	open htmlcov/index.html
	echo "Press ENTER to continue..."
	read
	rm -rf htmlcov
	rm .coverage

.ONESHELL:
formula: setup-formula
	set -ae
	cd Tap
	git pull
	git add Formula/walrus.rb
	git commit -S -m "walrus: $(version)"
	git push

test:
	pipenv run python tests/test.py
	rm -rf archive

pipenv-init:
	pipenv install --dev \
	    autopep8 \
	    codecov \
	    coverage \
	    doc8 \
	    pylint \
	    sphinx

pipenv-update:
	pipenv run pip install -U \
	    pip \
	    setuptools \
	    wheel
	while true; do \
            pipenv update && break ; \
        done
	pipenv install --dev
	pipenv clean

pipenv-deinit:
	pipenv --rm

update-maintainer:
	go run github.com/gaocegege/maintainer changelog
	go run github.com/gaocegege/maintainer contributor
	go run github.com/gaocegege/maintainer contributing

pypi-clean:
	mkdir -p dist sdist eggs wheels
	[ -d dist ] && find dist -iname '*.egg' -exec mv {} eggs \; || true
	[ -d dist ] && find dist -iname '*.whl' -exec mv {} wheels \; || true
	[ -d dist ] && find dist -iname '*.tar.gz' -exec mv {} sdist \; || true
	rm -rf build dist *.egg-info

pypi-dist: pypi-clean setup-version dist-pypi dist-pypitest

dist-pypi: pypi-clean setup-version
	pipenv run python setup.py sdist bdist_wheel

dist-pypitest: pypi-clean setup-version
	pipenv run python setup.py sdist bdist_wheel

pypi-register: pypi-dist
	twine check dist/* || true
	twine register dist/*.whl -r pypi --skip-existing
	twine register dist/python*.whl -r pypitest --skip-existing

pypi-upload:
	twine check dist/* || true
	twine upload dist/* -r pypi --skip-existing
	twine upload dist/python* -r pypitest --skip-existing

setup-version:
	pipenv run python scripts/setup-version.py

setup-formula: setup-version pipenv-update
	pipenv run python scripts/setup-formula.py

setup-manual: setup-version
	pipenv run rst2man.py share/walrus.rst > share/walrus.1

git-upload:
	git pull
	git add .
	git commit -S
	git push

git-after:
	git pull
	git add .
	git commit -S -m "Regular update after distribution"
	git push

git-release:
	go run github.com/aktau/github-release release \
	    --user JarryShaw \
	    --repo walrus \
	    --tag "v$(version)" \
	    --name "walrus v$(version)" \
	    --description "$$(git log -1 --pretty=%B)"
