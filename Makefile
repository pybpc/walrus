clean: pypi-clean
pipenv: pipenv-update
pypi: pypi-dist pypi-upload
maintainer: update-maintainer

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
	pipenv update
	pipenv install --dev
	pipenv clean

pipenv-deinit:
	pipenv --rm

update-maintainer:
	go run github.com/gaocegege/maintainer changelog
	go run github.com/gaocegege/maintainer contributor
	go run github.com/gaocegege/maintainer contributing

pypi-clean:
	mkdir -p sdist eggs wheels
	[ -d dist ] && find dist -iname '*.egg' -exec mv {} eggs \; || true
	[ -d dist ] && find dist -iname '*.whl' -exec mv {} wheels \; || true
	[ -d dist ] && find dist -iname '*.tar.gz' -exec mv {} sdist \; || true
	rm -rf build dist *.egg-info

pypi-dist: pypi-clean
	pipenv run python setup.py sdist bdist_wheel

pypi-register: pypi-dist
	twine check dist/* || true
	twine register dist/*.whl -r pypi --skip-existing
	twine register dist/*.whl -r pypitest --skip-existing

pypi-upload:
	twine check dist/* || true
	twine upload dist/* -r pypi --skip-existing
	twine upload dist/* -r pypitest --skip-existing
