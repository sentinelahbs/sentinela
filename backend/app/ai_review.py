"""
Segundo parecer de IA sobre alertas já disparados — chama a API do Claude
com alguns frames do clipe pra dar um veredito estruturado (furto provável
/ falso positivo provável / inconclusivo) + justificativa curta, ajudando
o dono da loja a decidir mais rápido sem precisar assistir o clipe inteiro
toda vez.

Roda em BACKGROUND, depois que o alerta já foi salvo e a box já recebeu a
resposta (ver receive_alert em routers/alerts.py) — nunca atrasa nem
derruba o envio do alerta principal. É um sinal complementar: qualquer
falha aqui (chave não configurada, clipe sem frame legível, API fora do
ar, resposta mal formada) só resulta em None, nunca propaga exceção pra
quem chamou.

Usa uma conta de API própria do projeto (ANTHROPIC_API_KEY no ambiente do
backend), separada de qualquer assinatura pessoal do Claude Code — ver
memória do projeto sobre esse ponto.
"""

import base64
import logging
import os
import tempfile
from enum import Enum

import cv2
from pydantic import BaseModel

log = logging.getLogger("ai_review")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
# Opus por padrão -- testado contra clipes reais e deu pareceres bem mais
# específicos/criteriosos que Haiku (que tendia a dar sempre a mesma
# resposta genérica) e Sonnet nos testes feitos durante o desenvolvimento
# dessa funcionalidade. Custo medido: ~$0.01-0.03 por alerta -- irrelevante
# perto da mensalidade por loja, mesmo em lojas de alto volume.
AI_REVIEW_MODEL = os.environ.get("AI_REVIEW_MODEL", "claude-opus-5")
# Quantos frames extrair do clipe -- mais que 1 dá contexto de sequência
# (testado: ajuda a notar "item não voltou pra cesta visível", por
# exemplo), mas cada frame a mais custa tokens de imagem extra.
_MAX_FRAMES = 3

SYSTEM_PROMPT = (
    "Você é um assistente de prevenção de perdas de uma loja de varejo (mercado). "
    "Você recebe algumas imagens sequenciais extraídas de um clipe de câmera de segurança, "
    "tiradas ao redor do momento em que um sistema automático sinalizou uma possível ação "
    "suspeita de um cliente ou funcionário (o motivo técnico do disparo vem junto na mensagem). "
    "Dê um veredito curto e uma justificativa breve (1-2 frases, em português) sobre se isso "
    "parece furto de verdade, um falso positivo (ex: cliente normal fazendo compras, funcionário "
    "repondo estoque, ajeitando roupa/bolsa), ou inconclusivo pela imagem disponível. Se houver "
    "mais de uma pessoa na cena, foque na que mais provavelmente motivou o alerta (geralmente a "
    "mais próxima da prateleira ou com o gesto mais evidente)."
)


class Veredito(str, Enum):
    provavel_furto = "provavel_furto"
    provavel_falso_positivo = "provavel_falso_positivo"
    inconclusivo = "inconclusivo"


class AlertaAnalise(BaseModel):
    veredito: Veredito
    justificativa: str


def _extract_frames(clip_bytes: bytes, max_frames: int = _MAX_FRAMES) -> list:
    """Extrai alguns frames (JPEG, em bytes) espaçados ao longo do clipe.
    Usa um arquivo temporário porque cv2.VideoCapture não lê direto de
    bytes em memória. Nunca levanta -- clipe corrompido, vazio ou num
    formato que o OpenCV não decodifica só resulta em lista vazia (quem
    chama trata isso como "sem imagem pra analisar", não como erro)."""
    frames = []
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(clip_bytes)
            tmp_path = f.name

        cap = cv2.VideoCapture(tmp_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            cap.release()
            return []

        positions = [int(total * i / (max_frames + 1)) for i in range(1, max_frames + 1)]
        for pos in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ok, frame = cap.read()
            if not ok:
                continue
            ok2, buf = cv2.imencode(".jpg", frame)
            if ok2:
                frames.append(buf.tobytes())
        cap.release()
    except Exception as exc:
        log.warning(f"[ai_review] Falha ao extrair frames do clipe: {exc}")
        return []
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
    return frames


def analyze_alert(clip_bytes: bytes, reason: str) -> "tuple[str, str] | None":
    """Retorna (veredito, justificativa) ou None se não deu pra analisar.
    Nunca levanta -- ver docstring do módulo."""
    if not ANTHROPIC_API_KEY:
        return None

    frames = _extract_frames(clip_bytes)
    if not frames:
        log.warning("[ai_review] Nenhum frame extraído do clipe, pulando análise")
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(frame).decode("utf-8"),
                },
            }
            for frame in frames
        ]
        content.append({
            "type": "text",
            "text": f"Motivo técnico do disparo automático: {reason}\n\nAnalise essas imagens e dê seu parecer.",
        })

        response = client.messages.parse(
            model=AI_REVIEW_MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            output_format=AlertaAnalise,
        )
        result = response.parsed_output
        return result.veredito.value, result.justificativa
    except Exception as exc:
        # Erro de rede, rate limit, resposta mal formada, o que for -- isso
        # é um sinal complementar, nunca pode derrubar o fluxo de alerta.
        log.warning(f"[ai_review] Falha ao chamar a API do Claude: {exc}")
        return None
