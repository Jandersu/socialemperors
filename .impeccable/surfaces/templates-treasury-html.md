---
version: 1
slug: "templates-treasury-html"
primary_target: "templates/treasury.html"
related_targets:
  - "templates/css/treasury.css"
  - "templates/css/portal-shell.css"
  - "templates/js/treasury.js"
---

# Tesouro

Mode: Operate. Extension of the existing minimal portal identity introduced for Rivais, as requested by the user's “refaça totalmente essa tela também”. No new visual world or global redesign.

## Intent

Players claim free game money, see their balance, and check previous claims. Replace the old text-heavy screen with one compact wallet panel: balance, initial bonus when available, and daily reward. Reduce explanation to essential context and short eligibility labels; keep help in a collapsed disclosure.

## Decisions

- Inherit blue #3b5998, neutral #f6f7fa, white, separator #e3e7ee, text #202b3d and muted #626d7d from the new Rivais screen. Use system-ui and restrained 32px/29px page titles.
- One bordered 12px wallet, flat reward rows, visible recent history. No decorative imagery, shadows, animation, or nested cards.
- Desktop rows align reward name, amount and action. Mobile reflows to name/amount followed by a full-width button. Preserve whole amounts and dates.
- Clearly identify the balance as dinheiro, separate from gold. Initial grant is unique; daily eligibility follows 24 hours after the previous claim. Values come from the overview, never hardcoded.
- Show the first three recent claims and keep the remainder of the existing 20-item history in a native disclosure. Help retains usage, free economy, no raids of this currency, no accumulated days and reloading the village.
- Display cooldown timestamps and capacity blockers with associated descriptions. Success and server errors remain visible through the base template.
- Preserve POST /treasury/claim, csrf_token and action=initial|daily. Move action to a hidden input before disabling the submit button for loading. Native forms and disclosures work without JavaScript.
- Extract the existing Rivais header/body styling to portal-shell.css without changing its appearance, so both screens share the same navigation. Other portal routes retain their current styles. Remove only unused Treasury selectors from management.css.

## Verification

One combined desktop/mobile pass at 1440/1920 and 390/320, including available grants, claimed/cooldown, history, maximum balance, maximum configured rewards, forms without JS, Enter submission, real independent claims, repeated claims, CSRF and signed-in admin navigation. Include a Rivais shell regression check. Fix material findings in one batch and confirm at most once. Run existing unit tests and JavaScript syntax checks. Independent finish reviewer reads the captures and source without rendering again.

## Resultado e documentação

A revisão independente terminou com **ship**, sem pendências. O único achado foi resolvido com o link **Atualizar** junto à data e hora do próximo resgate: ele consulta novamente o servidor por GET, sem liberar a ação pelo relógio do navegador.

O lote inicial passou em 96 verificações no navegador; a confirmação focada passou em 31, sem erros de JavaScript. Os 103 testes automatizados passaram, e os nove testes de gestão passaram novamente após o ajuste do link. As métricas de Rivais em desktop e celular foram preservadas pela extração do cabeçalho compartilhado. Os dados de teste ficaram isolados em `/tmp`, e as capturas permanecem ignoradas pelo Git.

O contexto confirmado está em [PRODUCT.md](../../PRODUCT.md), e as decisões observadas estão em [DESIGN.md](../../DESIGN.md). As fontes são o [template](../../templates/treasury.html), o [CSS do Tesouro](../../templates/css/treasury.css), o [cabeçalho compartilhado](../../templates/css/portal-shell.css) e o [JavaScript](../../templates/js/treasury.js). A expansão de escopo autorizada cobre Rivais e Tesouro; não autoriza redesenhar outras rotas.

## Boundaries

No changes to rewards, cooldowns, balances, payments, combat or administration. Synthetic accounts and money exist only in isolated test data under /tmp. Preserve the logo and game artwork.
