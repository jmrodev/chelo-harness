# 03. Integración con Daily Board y Metodologías Ágiles

## Dos repositorios, dos roles
El tablero involucra **dos repositorios distintos** y conviene no confundirlos:

| Rol | Repositorio | Qué aporta |
|---|---|---|
| Aplicación (el reproductor) | [`jmrodev/daily-board`](https://github.com/jmrodev/daily-board), rama `gh-pages` | El sitio estático: HTML, CSS y JS. Se descarga en cada ejecución del workflow. |
| Contenido (el tablero) | **El repo donde se instala** `board init` | Issues, PRs, milestones, `/docs`, `/dailies` y `/canales` que ves en pantalla. |

El workflow generado hace `actions/checkout` del **primero** para obtener la app.
El **segundo** no se configura en ningún lado: el JS del tablero lo deduce de su
propia URL de Pages (`js/state.js`, `detectCurrentRepoSlug`). Deployado en
`owner.github.io/repo/`, lee `owner/repo`. Para apuntarlo a otro repositorio se
usa el override explícito `?repo=owner/repo` en la URL del tablero.

Por eso `repository: jmrodev/daily-board` en el workflow **no** es un hardcodeo a
corregir: es de dónde baja la aplicación. Sustituirlo por el repo que instala el
workflow rompe el deploy, porque `actions/checkout` dejaría de encontrar el sitio.
Ese contrato está fijado por `BoardWorkflowContract` en `tests/test_board.py`.

## Daily Board como Frontend Ágil (GitHub Pages)
Chelo-Harness se integra de forma transparente con **[Daily Board](https://github.com/jmrodev/daily-board)**:
- Tablero Kanban Client-Side puro sobre GitHub Issues y Milestones.
- Etiquetas nativas de flujo: `status:todo`, `status:in-progress`, `status:blocked`, `status:done`.

## Flujo del Sprint:
1. **Inicialización**: `chelo-harness board init` inyecta el workflow y activa GitHub Pages.
2. **Selección del Issue**: En la Fase 0, el harness lee el Milestone activo y te permite vincular el Issue a trabajar, marcándolo automáticamente `status:in-progress`.
3. **Cierre Automático**: Al commitear con `chelo-harness commit`, se incluye `Closes #N`, cerrando el issue en GitHub y moviendo la tarjeta a `status:done` en el board.
