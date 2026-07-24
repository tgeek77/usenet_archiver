# Packaging targets. Application code: usenet_archiver/. Zipapp: scripts/build_zipapp.sh

.PHONY: zipapp clean-zipapp appimage clean-appimage test gui

zipapp:
	./scripts/build_zipapp.sh

clean-zipapp:
	rm -rf .zipapp_stage dist/usenet-archiver dist/usenet-archiver-*-zipapp.tar.gz

appimage: zipapp
	./scripts/build_appimage.sh

clean-appimage:
	rm -rf .appimage_stage dist/*.AppImage

test:
	python3 -m unittest discover -s tests -v

gui:
	python3 -m usenet_archiver
