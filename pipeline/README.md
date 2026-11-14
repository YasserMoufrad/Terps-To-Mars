# Terrain pipeline

The processing modules and synthetic raster tests will land in follow-up patches. The current Python test checks the shared data contract of the committed placeholder files. They are not NASA-derived terrain.

From the repository root, use Python 3.11 or newer:

```sh
python -m pip install -r pipeline/requirements.txt
python -m pipeline.validate_contract
python -m pytest pipeline/tests
```

Put raw source files in `pipeline/raw/`; never commit them.
