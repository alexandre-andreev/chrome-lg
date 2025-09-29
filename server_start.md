I'll quickly open `options.html` to see how to set the backend URL from the UI, so the instructions are accurate.

[6 tools called]

### ��������: ����� ������ ���७�� � LangGraph-������

- �����: ���७�� 㦥 ��⮢� ࠡ���� � ��� ������, �� ����� 㪠��� � ����ன���. �� ࠧ���㫨 ���� ���� �� LangGraph � `backend_lg` � �㤥� �ᯮ�짮���� ���.

### 1) �����⮢�� ���㦥��� � ����� �����
- ��ன� �ନ��� � `D:\_project\Chrome-lg\backend_lg`.
- ������� venv � ��⠭���� ����ᨬ���:
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r backend_lg\requirements.txt
```
- ��������, �� � ��୥ ९������ ���� `.env.local` � ���砬�:
```text
GEMINI_API_KEY=���_����
EXA_API_KEY=���_����

��⠭���� ���� ����᪮� ����� ���

```
$env:LANGGRAPH_VIZ_PATH="D:\_project\Chrome-lg\graph.svg"
```

- ������� �ࢥ�:
```powershell
cd D:\_project\Chrome-lg\backend_lg
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```
- �஢����, �� �⢥砥�:
```powershell
Invoke-WebRequest http://127.0.0.1:8010/ -UseBasicParsing | % Content
```
���������: {"status":"ok","engine":"langgraph"}

### 2) ��⠭���� � ����� ���७�� � Chrome
- ��ன� Chrome  ������ � ���᭮� ��ப�: `chrome://extensions/`
- ������ <����� ࠧࠡ��稪�>.
- ������ <����㧨�� �ᯠ��������> � �롥�� ����� �஥�� `D:\_project\Chrome-lg`.
- ��������, �� ���७�� ��⨢��.

### 3) ����ந�� URL ����� � ���७��
- � �ᯫ뢠�饬 ���� ���७�� ������ <����ன��> ��� ��ன� `options.html`.
- � ���� <URL ����� (FastAPI)> 㪠���:
```
http://127.0.0.1:8010
```
- ������ <���࠭���>.

�ਬ�砭��:
- ����७�� �� 㬮�砭�� �ᯮ���� ���� `backendBaseUrl` �� Chrome Storage; ���祭�� �� 㬮�砭�� - `http://localhost:8000`. ��� �㦭� � ���⠢��� ���� ���� `http://127.0.0.1:8010`.

### 4) �ᯮ�짮�����
- ��ன� ��࠭��� � ��㧥� (����).
- ��ன� ������� ������ ���७�� (���� �� ������  Side Panel ���뢠���� ��⮬���᪨).
- ������ ����� � ���� � ᠩ������� � ������ <��ࠢ���>.
- ����७�� ����ࠥ� ���㠫�� ���⥪�� ��࠭��� � ��뢠�� `/chat` ������ �����.

### 5) �஢�ઠ ����ன �離�
- � ᠩ������� ������ ���⮩ ����� �� ⥪�饩 ��࠭�� (���ਬ��: <��⪮: � �� �� ��࠭��?>).
- ��� ��࠭�� � ��������� ���⥭⮬ ���� �믮���� ���� EXA � ������� ���筨�� � �⢥�.

### 6) �᫨ �㦭� ���⮢��� ���� ��� �ࢨ�
- ����� ����᪠�� ⠪:
```powershell
Start-Process -WindowStyle Hidden -FilePath "D:\_project\Chrome-lg\backend_lg\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8010"
```

### 7) ����� ������
- �᫨ �⢥� <���⮩> ��� <���� �� ������> - �஢���� `.env.local`.
- �᫨ ���७�� ���� <�訡�� �ࢥ�: 404/500> - �஢����, �� ����஥� `http://127.0.0.1:8010` � <����ன��>.
- �᫨ �� ���뢠���� ᠩ������� - 㡥�����, �� ���७�� ����祭�, � ���஡�� �������� �������.

��⮢ ������, �᫨ ����� ��७��� �� � `README` � �������� ������ ����ண� ��४��祭�� URL ����� ����䥩�.