---
version: 1
slug: "templates-rivals-html"
primary_target: "templates/rivals.html"
related_targets:
  - "templates/css/rivals.css"
  - "templates/js/rivals.js"
---

# Rivais

Mode: Operate. Target: templates/rivals.html; related: templates/css/rivals.css, templates/js/rivals.js.

## Intent and scope

Players hosting this private game with friends need to compare rivals, attack, and check results. The user explicitly requested a complete redesign of this screen with only necessary text and a minimal, modern look. Replace its tall, prose-heavy composition with a compact village summary and a tabbed workspace. Scope is this route; inherit the portal's blue identity, existing logo, navigation, and game rules. No global brand redesign.

## Surface decisions

- Light neutral page, white surfaces, thin neutral separators, one existing blue action color. No decorative imagery or motion.
- System UI typography, 32px page title, 21px village name, 13–14px task content. Numeric values use tabular figures.
- Own village name, level, troops, attack, defense, and four resource balances remain visible.
- Three progressively enhanced tabs: Vilas, Classificação, Histórico. All panels remain accessible without JavaScript. Tabs support hash links and keyboard arrows/Home/End.
- Rival rows prioritize name, level, defense, possible loot, and Atacar. Disabled attacks explain the blocker. Brief rules live in a collapsed disclosure.
- Desktop uses aligned rows; mobile uses stacked rows with full-width attack buttons. Names wrap; large values retain their full amount.
- Keep all existing forms, CSRF and signed raid tokens, cooldowns, ranking, role-specific combat history, and server authority. A victory transfers 20% of each available ordinary resource; no economy changes.

## Verification contract

One combined browser pass covering desktop and mobile, empty/tutorial states, populated rivals/ranking/history, long names, large values, keyboard tabs, hash reload, no-JS fallback, and a real isolated-fixture raid. Fix material findings in one batch, then at most one confirmation. Existing 103 unit tests remain green. Independent finish review uses those captures and source, without another browser pass.

The fix batch preserves intrinsic resource widths, wraps resources to fewer columns when needed, stacks ranking metrics below village names on mobile, keeps local defense/loot labels available to assistive technology, puts village metadata below its name, and uses the correct singular for one troop or structure. Unused styles from the previous Rivais composition were removed from community.css; its village-renaming styles remain.

## Resultado e documentação

A revisão independente terminou com **ship**: quatro achados resolvidos e nenhuma pendência. A verificação concluída somou 93 verificações válidas no navegador, nenhum erro de JavaScript, larguras de 320 a 1920 px e 103 testes automatizados aprovados. Os cenários e o saque real usaram fixtures isoladas, sem dados fictícios acrescentados à produção.

O contexto confirmado está em [PRODUCT.md](../../PRODUCT.md), e o resultado visual executado está em [DESIGN.md](../../DESIGN.md). Esses documentos não ampliam o escopo além de Rivais.

## Non-goals

Do not redesign login, the game player, treasury, or administration. Do not replace the game's assets, add paid mechanics, change combat balance, or add decorative mock data to production.
