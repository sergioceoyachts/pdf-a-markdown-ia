# Instrucciones para la IA: documento PDF convertido a Markdown

> Sirve para **cualquier IA**: ChatGPT, Gemini, Claude, Copilot, Mistral, modelos locales…
> En las IAs de chat web, sube este archivo junto con `INDICE.md` del documento, o pega el bloque de abajo como primer mensaje.

```text
Vas a trabajar con un documento PDF convertido a Markdown para ahorrar tokens.
Estructura de la carpeta del documento:
- INDICE.md: capítulos con su rango de páginas (p. ej. "→ p71–79"). EMPIEZA SIEMPRE AQUÍ.
- paginas.md: una línea por página (tokens, figuras, tablas, tema). Solo si el índice no basta.
- pages/pNNN.md: texto LITERAL de cada página, con tablas y figuras en su posición.
- images/: figuras y planos (WebP). Id: p004-f2 = figura 2 de la página 4.
- tables/: cada tabla en .md y .csv. Id: p005-t1 = tabla 1 de la página 5.
- refs.md: id de cada figura o tabla con su página, posición, sección y texto cercano.

Reglas:
1. Usa INDICE.md para localizar la información y pídeme SOLO las páginas que necesites (por ejemplo "súbeme p012.md y p013.md"). Si al buscar una palabra aparece sobre todo en líneas ⟨ocr⟩ (texto leído de capturas o fotos), da prioridad a las páginas donde aparece en el texto normal, pero no descartes las otras: a veces la respuesta solo está en una imagen.
2. El texto es literal del documento original: cítalo tal cual, no lo reescribas ni lo completes.
3. Lo marcado ⟨ocr N %⟩ o ⟨ocr⟩ se leyó por OCR y puede tener errores; cuando te apoyes en ello, dilo. Lo marcado ⟦x⟧ es un símbolo gráfico (●, ≥, ✓…), no la letra x: tradúcelo con la tabla «Símbolos gráficos» de INDICE.md.
4. Debajo de cada figura hay una línea con su id, su posición y sus etiquetas (cotas, bornes, letras de piezas). Pide la imagen solo si de verdad necesitas verla.
5. Cita siempre la página y el id: "(p2, figura p002-f1)".
6. Si algo no aparece en el documento, dilo. No lo inventes, y menos en esquemas eléctricos, medidas o pasos de seguridad.
```

## Cómo usarlo en cada IA

| IA | Cómo |
|---|---|
| **Claude Code** (VS Code / terminal) | Abre la carpeta del kit y pregunta. Lee `CLAUDE.md` y la skill automáticamente |
| **OpenAI Codex CLI** | Abre la carpeta y pregunta. Lee `AGENTS.md` automáticamente |
| **Gemini CLI** | Abre la carpeta y pregunta. Lee `GEMINI.md` automáticamente |
| **Cursor, Windsurf, Aider, Zed** | Abre la carpeta y pregunta. Leen `AGENTS.md` |
| **GitHub Copilot** (VS Code) | Abre la carpeta y pregunta. Lee `.github/copilot-instructions.md` |
| **ChatGPT / Gemini / Claude web** | 1) Pega el bloque de arriba. 2) Sube `INDICE.md`. 3) Sube solo las páginas que te pida |
| **Proyectos de ChatGPT, Gems de Gemini, Projects de Claude** | Sube la carpeta `pages/` e `INDICE.md` como conocimiento y pon el bloque de arriba como instrucciones |
