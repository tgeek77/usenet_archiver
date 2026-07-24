# Packaging targets. Application code: usenet_archiver/. Zipapp: scripts/build_zipapp.sh

.PHONY: zipapp clean-zipapp test gui

zipapp:
	./scripts/build_zipapp.sh

clean-zipapp:
	rm -rf .zipapp_stage dist/usenet-archiver

test:
	python3 -m unittest discover -s tests -v

gui:
	python3 gui/usenet_archiver_gui.py
