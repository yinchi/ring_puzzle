#!/usr/bin/env bash

# This script builds the web UI and copies the output to the `docs` directory, which is what
# GitHub Pages serves.  Commit and push the changes to `docs` to update the live site.
cd web/
bun build index.html --outdir ../docs --minify