### ��� �⤠�� ���७�� ��㣨� ���짮��⥫�
- ��� �����࠭����: ��㡫���� ���७�� � ��������� ���� � HTTPS � ���४�� CORS.

#### ��ਠ��� �㡫���樨
- �㡫����� � Chrome Web Store (४���������)
  - ��ॣ������� ������ ࠧࠡ��稪� (ࠧ��� �����).
  - �����⮢�� ���ᠭ��, �ਭ���, ������, ����⨪� ���䨤��樠�쭮��.
  - � `manifest.json` ��⠢�� ⮫쪮 ����室��� ࠧ�襭��; 㪠��� �த���-����� API � `host_permissions`.
  - �������� ���� (�. ����) �� �㡫�筮� HTTPS-������ � ������� `backendBaseUrl` (�१ `options.html` ��� ��䮫� � `background.js`).
  - � ����� ��࠭���� CORS �� ��襣� `chrome-extension://<EXT_ID>` � �த���-������.

- ����७��� ࠧ��� (��� ��������)
  - ��� �������: ������� Developer Mode � �⠢��� "Load unpacked".
  - ��� �������� (GWS): ࠧ������ �१ Admin Console ��� "Force-install" � 㪠���� ZIP/URL.
  - ����: ����� CRX-䠩�� ��� Web Store ��� ���ᮢ�� ��⠭���� �����������.

- ���� (��易⥫쭮)
  - ������ FastAPI �� �� PaaS � HTTPS: ���ਬ��, Fly.io / Render / Railway / Cloud Run.
  - ����ன��:
    - ENV: `GEMINI_API_KEY`, `EXA_API_KEY`.
    - CORS: ࠧ���� `chrome-extension://<EXT_ID>`, ��� �����.
    - TLS: ⮫쪮 `https://...`.
  - � `manifest.json` �������� `host_permissions` ��� ��� ����� API.
  - �� ���������� ��࠭���� `"<all_urls>"`, �᫨ �� �ॡ����.

