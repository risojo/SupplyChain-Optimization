"""Narración hablada en el navegador (Web Speech API, voz femenina en español)."""
from __future__ import annotations

import json

import streamlit.components.v1 as components


def render_controles_narracion(texto: str, *, component_key: str = "inv_tts") -> None:
    """Botones Escuchar / Detener y estado, con guion en expander."""
    guion = texto.strip() or "No hay texto para narrar."
    texto_js = json.dumps(guion, ensure_ascii=False)

    components.html(
        f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  body {{
    margin: 0;
    font-family: system-ui, -apple-system, sans-serif;
    background: transparent;
    color: #e2e8f0;
  }}
  .fila {{
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }}
  button {{
    background: #f8fafc;
    color: #0f172a;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
  }}
  button:hover {{ background: #e2e8f0; }}
  #estado {{
    font-size: 14px;
    color: #94a3b8;
    min-width: 72px;
  }}
  .nota {{
    margin-top: 8px;
    font-size: 12px;
    color: #64748b;
    line-height: 1.4;
  }}
</style>
</head>
<body>
  <div class="fila">
    <button type="button" id="btn-escuchar">Escuchar</button>
    <button type="button" id="btn-detener">Detener</button>
    <span id="estado">Listo.</span>
  </div>
  <div class="nota">
    Use Escuchar / Detener. Funciona en Chrome o Edge con sonido activado.
    Refleja solo lo filtrado en esta pantalla.
  </div>
<script>
(function() {{
  const texto = {texto_js};
  const estado = document.getElementById('estado');
  let voces = [];

  function cargarVoces() {{
    voces = speechSynthesis.getVoices();
  }}
  cargarVoces();
  if (speechSynthesis.onvoiceschanged !== undefined) {{
    speechSynthesis.onvoiceschanged = cargarVoces;
  }}

  function elegirVoz() {{
    const preferidas = [
      /sabina|helena|paulina|monica|dalia|laura|female|mujer|woman/i,
    ];
    const es = voces.filter(v => (v.lang || '').toLowerCase().startsWith('es'));
    for (const rx of preferidas) {{
      const v = es.find(x => rx.test(x.name));
      if (v) return v;
    }}
    return es[0] || voces[0] || null;
  }}

  function hablar() {{
    if (!texto) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(texto);
    u.lang = 'es-MX';
    const voz = elegirVoz();
    if (voz) u.voice = voz;
    u.rate = 0.92;
    u.pitch = 1.05;
    u.onstart = () => {{ estado.textContent = 'Narrando...'; }};
    u.onend = () => {{ estado.textContent = 'Listo.'; }};
    u.onerror = () => {{ estado.textContent = 'Error de voz.'; }};
    speechSynthesis.speak(u);
  }}

  function detener() {{
    speechSynthesis.cancel();
    estado.textContent = 'Detenido.';
  }}

  document.getElementById('btn-escuchar').addEventListener('click', hablar);
  document.getElementById('btn-detener').addEventListener('click', detener);
}})();
</script>
</body>
</html>
        """,
        height=88,
        scrolling=False,
    )
