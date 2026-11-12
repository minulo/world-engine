Scripts of the detail-edges work (docs/BUILD_NOTES.md, section 25), kept as they were run. They read a preview world
built with: python -m worldengine build --profile preview --out <store>, and take its path as their first argument
where they ask for one; run them with PYTHONPATH=src from the repository's root. detail_base.py is the module as it
was before the change, for the before-and-after measurements.
