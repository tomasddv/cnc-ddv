# Nuevo: cierres mensuales y actualización desde Drive

El nuevo procesamiento está en `scripts/cerrar_mes_drive.py` y su programación en `.github/workflows/cierre_cnc_ddv.yml` **en la raíz del proyecto**. El instructivo está en `scripts/COMO_CONFIGURAR_CIERRE_AUTOMATICO.md`.

La app muestra períodos **cerrados**: 2025-05 a 2026-10 del histórico inicial y, desde 2026-11, solo los meses presentes en el índice privado `cierres_index.json`. La venta diaria del mes corriente ya no se incorpora al tablero.

Si un cliente desaparece del reporte de activos, se conserva como cliente histórico y se registra `baja_inferida_mes`. Esto **no significa que se conozca el día exacto de anulación**. La fuente original de anulados continúa intacta.

---

# CNC DDV — Supervisores y Licencia de Alcohol (05/11/2026)

## Filtros nuevos

- **Supervisor** (barra lateral): `Todos`, `BRUNO ISMAEL`, `HERNAN CASCO`.
  El filtro se aplica al origen de datos antes de calcular cartera, CNC,
  ranking, planes y auditoría. La cartera del supervisor **ANIBAL VITI**
  permanece dentro de `Todos`, sin atribuirla a Bruno o Hernán.
- **Negocio CZA:** solo clientes con **`Licencia alcohol = SI`** en el maestro
  de 6.400 clientes; los de `NO` se excluyen de vigencia CZA, CNC, planes,
  ranking, indicadores y exportaciones de CZA.
- **Negocio UNG:** corresponde al código interno `NABS` (mapeo provisional
  del proyecto). Incluye **todos** los clientes elegibles con promotor,
  independientemente de si tienen licencia de alcohol.
- Al elegir **Todos** los negocios, cada negocio conserva su universo:
  CZA con licencia y UNG/NABs sin esa restricción.
- La pestaña **Respuestas BEES Force** mantiene su filtro propio:
  al elegir `CZA` también usa licencia SI; en `Todos` preserva las
  encuestas de origen, incluso las que no pertenecen al universo
  CNC elegible.

## Fuentes incorporadas

- Licencia: columna `Licencia alcohol` de `reporte con anulados.xlsx`.
  En el padrón disponible: 2.385 SI, 4.015 NO.
- Supervisor: `Estructura Distribuidores 2026.xlsx`, en la tabla
  `data/supervisores_estructura_2026.csv` para futuras recargas.
  Promotores con supervisor mapeado: BRUNO ISMAEL, HERNAN CASCO,
  ANIBAL VITI. Hay variantes de nombre (orden de apellido/nombre,
  FABRE / FAVRE) normalizadas sin cambiar el origen.

**Limitación histórica:** la licencia y la estructura comercial corresponden
al padrón y la estructura disponibles en esta copia; no existe en las
fuentes utilizadas una serie mensual de cambios de licencia/supervisor.
El estado de alta/baja y las ventas **sí** se reconstruyen por mes.

## Cómo abrir la versión local

1. Cerrá todas las ventanas de la versión anterior.
2. Extraé el ZIP en una carpeta nueva, no encima de la anterior.
3. Si guardaste planes/gestiones, copiá `data/cnc_local.sqlite` de la
   carpeta anterior a la nueva **con la app cerrada**.
4. Ejecutá `INICIAR_CNC_LOCAL.bat` y abrí `http://localhost:8515`.
   Si el puerto está ocupado, revisá `diagnostico_inicio.txt`.

**Se conservan** la vigencia histórica 3M, CNC por promotor 3/6/12M,
selección masiva de planes y el historial de BEES Force.

---

# CORRECCIÓN ANTIGÜEDAD CNC — 05/11/2026

No toda ausencia de compra implica CNC. Para U3M, U6M y U12M el cliente
debe haber estado dado de alta **desde el primer día de los N meses
calendario analizados**, además de estar vigente al cierre, tener promotor
y no registrar compras en ese negocio dentro de la ventana.

**Caso testigo:** Cliente 5542, LA PREVIA RURAL 3, alta 17/09/2026.
En 2026-10 NO puede ser CNC 3M/6M/12M, aunque no haya comprado Marketplace.

Corte para cierre octubre/2026:
* U3M: alta hasta 01/08/2026; no compra ago-sep-oct.
* U6M: alta hasta 01/05/2026; no compra may-oct.
* U12M: alta hasta 01/11/2025; no compra nov/2025-oct/2026.

Se usan MESES CALENDARIO COMPLETOS y no 90 días exactos, ya que las
ventas suministradas están consolidadas por mes. La vigencia histórica
sigue mostrando clientes con alta o baja durante la ventana; la condición
de antigüedad cambia exclusivamente los indicadores CNC, ranking,
seguimiento y elegibilidad de planes de acción.

## Windows
1. Extraé el ZIP en una carpeta NUEVA.
2. Si tenés planes guardados, cerrá los tableros y copiá el archivo
   `data/cnc_local.sqlite` de la carpeta anterior a esta.
3. Ejecutá `INICIAR_CNC_LOCAL.bat`. Abre en localhost:8515 (o 8516).

---

# Nueva solapa: CNC por promotor (3M, 6M, 12M)

En la solapa **CNC por promotor**, elegir **3 meses**, **6 meses** o **12 meses**.
El período termina siempre en el mes elegido en el filtro lateral **Período de cierre**.

- Se consideran solamente clientes **vigentes al cierre** y con **promotor asignado**.
- **Clientes CNC**: clientes únicos por promotor que NO tuvieron compra neta positiva
  en el negocio seleccionado en ninguno de los meses del período. Si elegís
  **Todos** los negocios, cada cliente cuenta una sola vez por promotor, aunque
  sea CNC en CZA, NABs, Aguas y Marketplace simultáneamente.
- **Casos CNC**: combinaciones cliente-negocio sin compra (pueden ser más que
  clientes únicos).
- **Clientes activos**: clientes únicos con promotor y vigencia al cierre en el
  universo seleccionado.
- **% de cartera CNC**: clientes CNC únicos / clientes activos del promotor.
- Para 2026-10: 3M = agosto a octubre de 2026; 6M = mayo a octubre de 2026;
  12M = noviembre de 2025 a octubre de 2026.
- Si faltan meses para un horizonte, muestra **No verificable** y detiene el
  ranking; no interpreta ausencia de datos como ausencia de compras.
- Respeta negocio, promotor, localidad y búsqueda general; el filtro
  lateral «Cartera» no afecta este ranking.
- Se puede exportar el cuadro a CSV para Excel y ordenar por promotor o por CNC.

Las cohortes son **acumulativas**: U12M está incluido en U6M, y U6M en U3M.
**No sumarlas.** MATCH sigue sin mapeo validado; UNG→NABs es provisional.
La asignación histórica de promotor no puede reconstruirse si cambió con
posterioridad usando únicamente el maestro actual.

Se mantienen los planes masivos, vigencia histórica, BEES Force y auditoría.
Para probar en Windows: extraer el ZIP completo, ejecutar
**INICIAR_CNC_LOCAL.bat** y abrir **http://localhost:8515**.
Si tenías planes guardados, copiar `data/cnc_local.sqlite` desde la versión
anterior con la app cerrada y **antes de ejecutar** la nueva.

---

# CNC DDV · versión con selección múltiple y planes compartidos

# CNC DDV — versión con planes de acción masivos (05/11/2026)

## NUEVO: asignar el mismo plan a varios clientes

1. En **Planes de acción y contactos**, elegí mes, negocio, promotor y búsqueda.
2. En la tabla, **marcá varias casillas** para un grupo de clientes. También podés activar
   **Seleccionar TODOS los clientes del listado filtrado** para aplicar el plan a todos los
   CNC U3M elegibles que aparecen con esos filtros.
3. Al marcar **dos o más clientes**, aparece el **formulario de plan compartido**.
   Completá objetivo, acción concreta, fecha compromiso y estado.
4. Opcionalmente, escribí un motivo, responsable o supervisor común.
   Si dejás **responsable común** vacío, cada cliente conserva su promotor asignado.
   Si dejás **motivo común** vacío, cada cliente conserva su motivo de plan o Force;
   cuando no hay motivo relevado, queda vacío, sin inventar una encuesta.
5. La opción **Sobrescribir también los planes existentes** está desmarcada por defecto.
   Con la opción desmarcada, solo se crean planes donde todavía no hay uno.
6. Presioná **Guardar el plan para los N seleccionados**. Aparece un mensaje con
   cuántos planes se guardaron y cuántos quedaron protegidos.
7. Para **un único cliente**, marcá una fila y se abre el formulario individual de siempre.

La selección no incluye bajas del período ni clientes sin promotor. Se aplica únicamente
a CNC U3M vigentes de CZA/NABs. Se respeta el mes seleccionado en la clave de cada plan.
Los contactos/visitas no se generan automáticamente: deben registrarse por separado.

## Abrir en Windows

1. Extraé TODO el ZIP en una carpeta nueva, no ejecutes el .bat desde el ZIP.
2. Cerrá las versiones anteriores de Streamlit.
3. Ejecutá `INICIAR_CNC_LOCAL.bat` dentro de `CNC_DDV_LOCAL`.
4. Abrí http://localhost:8515 (o 8516 si ese puerto estaba ocupado).
5. Si ya tenés planes/contactos, copiá previamente desde la instalación vieja
   `data/cnc_local.sqlite` a la carpeta `data` nueva **con el tablero cerrado**.
6. Si no abre, adjuntá `diagnostico_inicio.txt`.

## Alcance y seguridad

Los datos de ventas y las respuestas BEES Force siguen siendo una copia privada y
no se sincronizan automáticamente. El ZIP contiene datos comerciales: **no publicarlo
íntegro en un repositorio público**. MATCH no está mapeado y UNG→NABs es provisional.
La interfaz se probará en tu Windows; en este entorno se ejecutaron pruebas automáticas
de los cálculos, el almacenamiento y la selección masiva.

## Información técnica

El tablero usa Streamlit. `planes_masivos.py` prepara una fila independiente por
cliente/mes/negocio. `almacen_local.guardar_planes_local_masivo` guarda todos los
registros en una transacción SQLite. Google Sheets usa una función de escritura
por lotes cuando está configurado el modo online.

Las pruebas viven en `tests/`, en particular `tests/test_planes_masivos.py`.


### Filtrar PDA por motivo relevado en la app de promotores

La pestaña «Planes de acción y contactos» ahora agrega: motivo del promotor, detalle de la respuesta y fecha.
El filtro «Motivo relevado por el promotor» opera sobre el período seleccionado. Las opciones son
Todos, Sin dinero, Cerrado, Compra en súper/mayorista, Otro y Sin relevar.
La selección múltiple y «Seleccionar TODOS» solo actúan sobre las filas resultantes del filtro.
Los planes nuevos conservan el motivo informado por el promotor y, cuando falta, recurren a Force.
No marca las tareas Force como validadas ni modifica las respuestas de relevamiento.
