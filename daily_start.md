### ���� ����� (����ன�� ���㦥���)
```powershell
# 1) ��३� � ����
cd D:\_project\Chrome-lg\backend_lg

# 2) ������� � ��⨢�஢��� venv (���� ࠧ)
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

# � linux:
```
source .venv/bin/activate
```

# 3) ��⠭����� ����ᨬ��� (���� ࠧ; �� ���������� - �������)
```
pip install -r .\requirements.txt

```
#linux (��ண� � ��⠫��� backend_lg)

```
pip install -r ./requirements.txt
```
### ��६���� �।� (�� ⥪���� ���� PowerShell)
```powershell
# ����
$env:GEMINI_API_KEY="���_GEMINI_API_KEY"
$env:EXA_API_KEY="���_EXA_API_KEY"

# ��ਬ��� �⢥�
$env:STREAMING_ENABLED="1"

# ���㠫����� ��� (mermaid �㤥� ����㯥� �� /graph)
$env:LANGGRAPH_VIZ="1"
$env:LANGGRAPH_VIZ_PATH="D:\_project\Chrome-lg\graph.svg"

# (��樮���쭮) ��࠭�஢���� �⪫���� ��� EXA
$env:EXA_CACHE_DISABLED="1"
```

### ���� �ࢥ�
```powershell
# (�� ����� D:\_project\Chrome-lg\backend_lg, venv ��⨢�஢��)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010

```
# ��� ����᪠ � linux

```
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```


### ������ �஢�ન
```powershell
# ���஢�/���䨣�
Invoke-RestMethod -Uri http://127.0.0.1:8010/debug/health

# ���㠫����� ��� (��ଥ��-⥪��; ��⠢�� � mermaid.live)
Invoke-WebRequest -Uri http://127.0.0.1:8010/graph -OutFile D:\_project\Chrome-lg\graph.mmd
```

### ��������� ����� (��⪠� �����)
```powershell
cd D:\_project\Chrome-lg\backend_lg
.\.venv\Scripts\Activate.ps1

# � �⮩ �� ��ᨨ:
$env:GEMINI_API_KEY="���_GEMINI_API_KEY"
$env:EXA_API_KEY="���_EXA_API_KEY"
$env:STREAMING_ENABLED="1"
$env:LANGGRAPH_VIZ="1"
$env:LANGGRAPH_VIZ_PATH="D:\_project\Chrome-lg\graph.svg"
$env:EXA_CACHE_DISABLED="1"

.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

- ��� ���㠫쭮�� ����஫� ��� ��ன� `http://127.0.0.1:8010/graph` � �� ����室����� ��⠢�� ⥪�� � Mermaid Live Editor (`https://mermaid.live`).
