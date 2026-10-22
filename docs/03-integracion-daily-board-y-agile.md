# 03. Integración con Daily Board y Metodologías Ágiles

## Daily Board como Frontend Ágil (GitHub Pages)
Chelo-Harness se integra de forma transparente con **[Daily Board](https://github.com/jmrodev/daily-board)**:
- Tablero Kanban Client-Side puro sobre GitHub Issues y Milestones.
- Etiquetas nativas de flujo: `status:todo`, `status:in-progress`, `status:blocked`, `status:done`.

## Flujo del Sprint:
1. **Inicialización**: `chelo-harness board init` inyecta el workflow y activa GitHub Pages.
2. **Selección del Issue**: En la Fase 0, el harness lee el Milestone activo y te permite vincular el Issue a trabajar, marcándolo automáticamente `status:in-progress`.
3. **Cierre Automático**: Al commitear con `chelo-harness commit`, se incluye `Closes #N`, cerrando el issue en GitHub y moviendo la tarjeta a `status:done` en el board.
