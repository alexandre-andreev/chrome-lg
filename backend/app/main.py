import os
import logging
import re
from typing import Any, Dict, List, Optional
from pathlib import Path

from dotenv import load_dotenv

# --- Environment Loading ---
project_root = Path(__file__).resolve().parents[2]
env_path = project_root / '.env.local'

if env_path.exists():
	load_dotenv(dotenv_path=env_path)
else:
	load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import google.generativeai as genai
#from google.generativeai import types as ga_types
from exa_py import Exa

# --- API Clients Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EXA_API_KEY = os.getenv("EXA_API_KEY")

if not GEMINI_API_KEY:
	logger.critical("CRITICAL: GEMINI_API_KEY not found. Please check your .env.local file.")
else:
	logger.info("GEMINI_API_KEY loaded successfully.")

if not EXA_API_KEY:
	logger.critical("CRITICAL: EXA_API_KEY not found. Please check your .env.local file.")
else:
	logger.info("EXA_API_KEY loaded successfully.")

try:
	if GEMINI_API_KEY:
		genai.configure(api_key=GEMINI_API_KEY)
	
	if EXA_API_KEY:
		exa_client = Exa(api_key=EXA_API_KEY)
	else:
		exa_client = None
except Exception as e:
	logger.critical(f"Failed to configure API clients: {e}")
	exa_client = None

# --- Helpers ---
def sanitize_answer(text: str) -> str:
	"""Normalize answer while preserving newlines and simple lists.

	- Convert markdown links [text](url) -> text
	- Remove stray bracketed tokens
	- Preserve single newlines; collapse 3+ newlines into 2
	- Normalize markdown bullets (-, *) to '- '
	- Trim trailing spaces on each line
	"""
	if not text:
		return text
	# Convert markdown links [text](url) -> text
	text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
	# Remove stray bracketed tokens [Женщинам] -> Женщинам
	text = re.sub(r"\[([^\]]+)\]", r"\1", text)
	# Normalize newlines
	text = text.replace("\r\n", "\n").replace("\r", "\n")
	# Normalize bullets to '- '
	text = re.sub(r"\n\s*[-*]\s+", "\n- ", text)
	# Collapse 3+ consecutive newlines into 2
	text = re.sub(r"\n{3,}", "\n\n", text)
	# Trim trailing spaces on each line and overall
	text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
	return text

# --- Exa Search helper ---
def search_exa(query: str) -> List[Dict[str, Any]]:
	if not exa_client:
		logger.error("Exa client not configured or API key is missing.")
		return [{"error": "Exa client not configured"}]
	try:
		results = exa_client.search_and_contents(
			query,
			num_results=3,
			text={"max_characters": 1000},
		)
		return [
			{
				"title": res.title,
				"url": res.url,
				"snippet": res.text,
			}
			for res in results.results
		]
	except Exception as e:
		logger.error(f"Exa API search failed: {e}")
		return [{"error": f"Search failed with exception: {e}"}]

# --- Define Gemini Tool (dict-based FunctionDeclaration) ---
search_exa_tool = {
	"function_declarations": [
		{
			"name": "search_exa",
			"description": "Search the web for relevant sources using Exa",
			"parameters": {
				"type": "object",
				"properties": {
					"query": {"type": "string", "description": "Search query in natural language"}
				},
				"required": ["query"]
			}
		}
	]
}

# --- Gemini Model with Tool ---
model = genai.GenerativeModel(
	model_name="gemini-2.5-flash",
	tools=[search_exa_tool],
) if GEMINI_API_KEY else None

# --- FastAPI App & Pydantic Models ---
app = FastAPI(title="Chrome-bot Backend", version="1.3.2")
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

class ChatRequest(BaseModel):
	message: str
	page_url: Optional[str] = None
	page_title: Optional[str] = None
	page_text: Optional[str] = None

class ChatResponse(BaseModel):
	answer: str
	sources: List[Dict[str, Any]] = []

@app.get("/")
async def root() -> Dict[str, Any]:
	return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
	if not model:
		raise HTTPException(status_code=500, detail="Gemini model is not configured. Check API key.")

	user_message = (payload.message or "").strip()
	if not user_message:
		raise HTTPException(status_code=400, detail="Empty message")

	chat_session = model.start_chat()

	system_prompt = (
		"Ты — умный ассистент, специализируешься на анализе веб-страниц в браузере. "
		"Отвечай строго по контексту текущей страницы. "
		"Если контекста достаточно — не выполняй поиск. Если данных не хватает — вызови инструмент `search_exa`. "
		"Формат ответов: каждую отдельную мысль начинай с новой строки. "
		"Если перечисляешь факты/события/шаги — выводи их как простой список, каждый пункт с новой строки и с префиксом '- '. "
		"Без ссылок и служебных пометок. Давай ясные короткие ответы (до 10 предложений; при уточнении — до 20)."
	)

	prompt_parts: List[str] = [system_prompt]
	ctx_lines: List[str] = []
	if payload.page_url:
		ctx_lines.append(f"URL: {payload.page_url}")
	if payload.page_title:
		ctx_lines.append(f"TITLE: {payload.page_title}")
	if payload.page_text:
		snippet = payload.page_text.strip().replace("\n", " ")[:2000]
		if snippet:
			ctx_lines.append(f"TEXT: {snippet}")
	if ctx_lines:
		prompt_parts.append("КОНТЕКСТ СТРАНИЦЫ:\n" + "\n".join(ctx_lines))
	prompt_parts.append("ВОПРОС ПОЛЬЗОВАТЕЛЯ:\n" + user_message)

	final_prompt = "\n\n".join(prompt_parts)

	try:
		response = chat_session.send_message(final_prompt)
		parts = response.candidates[0].content.parts if response.candidates else []

		# Find a function_call among parts if present
		fn_call = None
		for p in parts:
			if getattr(p, "function_call", None):
				fn_call = p.function_call
				break

		if fn_call and fn_call.name == "search_exa":
			query = fn_call.args.get("query") if hasattr(fn_call, "args") else None
			if not query:
				query = user_message
				if payload.page_title:
					query = f"{user_message} {payload.page_title}"
			logger.info(f"Gemini requested search with query: '{query}'")
			search_results = search_exa(query)

			tool_content = {
				"role": "tool",
				"parts": [{
					"function_response": {
						"name": "search_exa",
						"response": {"results": search_results}
					}
				}]
			}
			second_response = chat_session.send_message(tool_content)
			# Safely extract text
			answer_text = getattr(second_response, "text", "") or ""
			answer_text = sanitize_answer(answer_text)
			if answer_text:
				return ChatResponse(answer=answer_text, sources=search_results)
			else:
				# Fallback: synthesize a brief answer as a simple list, no links
				bullets: List[str] = []
				for it in (search_results or [])[:3]:
					snip = (it.get("snippet") or "").strip().replace("\n", " ")
					if snip:
						bullets.append(snip)
				fallback = ("- " + "\n- ".join(bullets))[:600] if bullets else "Данных недостаточно для краткого ответа."
				return ChatResponse(answer=sanitize_answer(fallback), sources=search_results)

		# No function call: return direct text if available
		answer_text = getattr(response, "text", "") or ""
		if not answer_text:
			texts = []
			for p in parts:
				if getattr(p, "text", None):
					texts.append(p.text)
			answer_text = " ".join(texts)
		if not answer_text:
			logger.error(f"Unexpected empty response from Gemini: {response}")
			answer_text = "Не удалось получить содержательный ответ."
		return ChatResponse(answer=sanitize_answer(answer_text))

	except Exception as e:
		logger.exception(f"Error during Gemini chat: {e}")
		msg = str(e)
		if "ResourceExhausted" in msg or "429" in msg or "quota" in msg.lower():
			# Graceful fallback using Exa only (no links, no disclaimers)
			query = user_message
			if payload.page_title:
				query = f"{user_message} {payload.page_title}"
			results = search_exa(query)
			if results and not results[0].get("error"):
				bullets: List[str] = []
				for it in results[:3]:
					snip = (it.get("snippet") or "").strip().replace("\n", " ")
					if snip:
						bullets.append(snip)
				fallback = ("- " + "\n- ".join(bullets))[:600] if bullets else "Данных недостаточно для краткого ответа."
				return ChatResponse(answer=sanitize_answer(fallback), sources=results[:3])
			raise HTTPException(status_code=503, detail="Gemini rate limit. Поиск недоступен.")
		if "API key not valid" in msg:
			raise HTTPException(status_code=500, detail="Ключ API для Gemini недействителен. Проверьте .env файл.")
		raise HTTPException(status_code=500, detail="Произошла внутренняя ошибка сервера при общении с моделью.")


