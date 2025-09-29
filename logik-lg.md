��� ��⪨� �������ਨ � 㧫�� ��襣� ���:

- prepare_context:
  - ���樠������� `graph_trace`, `notes`, `focus`, 㪮�稢��� `page.text` �� ~24k ᨬ�����. ��⮢�� �室��� ���ﭨ� ��� ᫥����� 蠣��.

- chunk_notes:
  - �᫨ ⥪�� ��࠭��� ������, ०�� �� �ࠣ����� � � ������� LLM ��������� �� 12 ���⪨� �㭪⮢-����⮪ (���祢� 䠪��/����/�ନ��), ᪫��뢠�� �� � `notes`.

- build_search_query:
  - �� �᭮�� `user_message`, `page` � `notes` ���� LLM ᨭ⥧�஢��� 1-3 ��������� ���-�����. ���࠭�� `search_queries`, `search_query` �, �� ����稨, `page.host`.

- exa_search:
  - ��⠥��� �믮����� EXA-���� �� 1-3 ᣥ���஢���� ����ᠬ. �᫨ ����/�訡�� - ������ `research`-fallback. ���࠭�� `search_results`, ���⠢��� `used_search=True`, `decision="search_always"`.

- compose_prompt:
  - ����ࠥ� 䨭���� �஬��: ��⥬�� ������樨, URL/TITLE, �ਮ���� ���窨 ���⥭�, STRUCTURED-���� (PRODUCT/BRAND/PRICE), ����� `TEXT`, `NOTES`, ⮯-᭨����� �� `search_results`, � ᠬ �����. ������ � `draft_answer`.

- call_gemini:
  - ��ࠢ��� `draft_answer` � ������ � ���� १���� � `final_answer`.

- postprocess_answer:
  - ����� ࠧ����/��ત���, ��ଠ����� ��७��� � ��થ�� ᯨ᪮�.

- ensure_answer:
  - �᫨ `final_answer` ����, ������ ������� 䮫��: ���� ��⪨� ᯨ᮪ �� `notes` (� �ਮ��⮬ �㭪⮢ � �᫠��), ���� ���⪨� ᭨���� �� `page.text`.

- finalize:
  - ��⠢��� ⮫쪮 ⮯-3 `search_results` � �����蠥� �믮������.

���⢥ত���� ���㠫���樨:
- ����� ���⨭�� �� ᮧ������ ��-�� ��࠭�祭�� ���ᨨ langgraph, �� ��ଥ��-����ࠬ�� ��� �⤠���� �� `GET /graph`. �� ����� ���㠫���஢��� � ��㧥� �१ Mermaid Live [mermaid.live](https://mermaid.live/).

- ����� �������:
  - �᫮���� ࠧ����� ��᫥ `prepare_context`: �᫨ ⥪�� ����让 - ��� � `chunk_notes`, ���� �ࠧ� � `build_search_query`.
  - ����窠 ��᫥ ���᪠: `compose_prompt`  `call_gemini`  `postprocess_answer`  `ensure_answer`  `finalize`.

- �᫨ �����, ���� ������� � �஬�� ��������� ��� ��� ���� `focus`-ᥣ���⮢ (ᥩ�� `focus` �ଠ�쭮 �����ঠ� � `compose_prompt`, �� 㧥� ���ᢥ⪨ `_prepare_focus` �� ��뢠����).
