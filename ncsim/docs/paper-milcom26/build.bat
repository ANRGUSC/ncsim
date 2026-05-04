@echo off
REM Build script for the IEEE Milcom 2026 paper.
REM Usage: build.bat
setlocal
set TARGET=main
pdflatex -interaction=nonstopmode %TARGET%.tex
bibtex %TARGET%
pdflatex -interaction=nonstopmode %TARGET%.tex
pdflatex -interaction=nonstopmode %TARGET%.tex
endlocal
