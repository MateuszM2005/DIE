.PHONY: web-setup web desktop docker help

WEB := DIE-TS
DESKTOP := DIE_Py

help:
	@echo "make web-setup  - install JS + Python deps for the browser game"
	@echo "make web        - build TypeScript and run Django on 0.0.0.0:8000"
	@echo "make desktop    - install pygame/Pillow and launch the desktop game"
	@echo "make docker      - build and run the browser game in Docker (port 8000)"

web-setup:
	cd $(WEB) && npm install
	cd $(WEB) && python -m venv .venv
	$(WEB)/.venv/bin/pip install -r $(WEB)/requirements.txt || $(WEB)/.venv/Scripts/pip install -r $(WEB)/requirements.txt

web:
	cd $(WEB) && npm run build
	cd $(WEB) && python manage.py migrate --noinput
	cd $(WEB) && python manage.py runserver 0.0.0.0:8000

desktop:
	cd $(DESKTOP) && python -m pip install -r requirements.txt
	cd $(DESKTOP) && python main.py

docker:
	docker compose up --build
