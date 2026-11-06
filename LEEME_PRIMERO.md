# DDV | CNC conectados · tablero principal + relevamiento móvil

## NUEVO · Cierres mensuales automáticos desde Drive

**La app local sigue funcionando con el snapshot incluido.** En la nube, el nuevo procesador de cierres ya está escrito, pero **no corre hasta que se configuren las credenciales y permisos** en GitHub y Streamlit.

- Carpeta fuente de Drive: `planificacion` (`1cukgXLUaPsEDK_yD7tSwgaBFZAbiDUot`).
- Solo leer `ventadiaria noviembre.txt`/`venta noviembre.txt` cuando haya terminado noviembre. `ventadiaria.txt` del mes en curso está excluido.
- `reporte de clientes.xlsx` debe estar actualizado **después** del cierre; si sigue fechado 26/10/2026, noviembre queda pendiente.
- Quien figure en el padrón anterior y no en el nuevo, se considera **baja detectada en ese mes**. No se inventa un día exacto.
- Clientes y ventas se guardan por mes en la carpeta privada `CNC privados` y se publica un índice `cierres_index.json`; las vistas anteriores no cambian.
- Cuando el cierre esté disponible, en la barra lateral del tablero principal aparece **Activar campaña U3M del cierre**. Así se generan tareas del mes para la app de promotores sin tocar las respuestas de meses previos.
- El proceso de Google Drive no se encarga de actualizar automáticamente respuestas Force ni planes de acción; ambos tienen fuentes independientes.

**Pasos de configuración:** `CNC_DDV_LOCAL/scripts/COMO_CONFIGURAR_CIERRE_AUTOMATICO.md`. Incluye el flujo de GitHub Actions y los Secrets necesarios.


**Versión local de prueba.** Los dos tableros se comunican por una misma base SQLite. 
No es un despliegue público y no se están enviando respuestas por Internet.

## Iniciar en Windows

1. Extraé **todo el ZIP** (no ejecutes archivos dentro del ZIP).
2. Ejecutá `INICIAR_AMBOS.bat` en esta carpeta (o abrí por separado los BAT de cada app).
3. **Tablero principal:** http://localhost:8515 (si el puerto está ocupado, 8516).
4. **Relevamiento de promotores:** http://localhost:8520.
5. En la app móvil de prueba, elegí tu promotor o ingresá el código de un cliente asignado, respondé un cliente y volvé a **Seguimiento relevamientos** en el tablero principal.

Ambas aplicaciones comparten `datos_compartidos/relevamientos.sqlite`. Al iniciar por primera vez
se carga la campaña de octubre 2026: 268 clientes únicos y 357 casos CZA/UNG.
Cada respuesta por cliente se aplica a CZA y UNG si corresponde. Una persona puede aparecer
una sola vez en la lista del promotor, incluso si es CNC de ambos negocios.


## Nuevo: planes de acción filtrados por motivo del promotor

1. Abrí **Planes de acción y contactos** del tablero principal.
2. En «Filtrar planes por motivo relevado por el promotor» elegí: Todos, Sin dinero, Cerrado, Compra en súper/mayorista, Otro o Sin relevar.
3. La tabla muestra ahora **Nombre de fantasía, Razón social, Código, Negocio, Promotor, Motivo promotor, Detalle del promotor, Fecha relevada, Motivo Force y Estado del plan**.
4. Podés seleccionar varias filas o «Seleccionar TODOS» **solo dentro del motivo y demás filtros activos**, y asignar un mismo plan.
5. Si el motivo común queda vacío, el motivo del plan se determina en este orden: motivo manual ya guardado; relevamiento del promotor; BEES Force.
6. Los relevamientos de la app de promotores **no se consideran automáticamente tareas BEES Force validadas**.

**El motivo depende del mes de la campaña cargada.** Si todavía no hubo respuesta o no existe una campaña para ese período, figurará «Sin relevar». No se modifican respuestas antiguas.
**Nota sobre duplicados:** el promotor releva cada cliente una sola vez, pero un cliente CNC de CZA y UNG puede aparecer en dos filas del tablero de planes, porque el PDA se guarda por cliente + negocio + mes.

## Vista histórica sin solapa visible

La solapa «Vigencia histórica · 3 meses» se ocultó. El cálculo de vigencia
de tres meses se mantiene en los KPI y en la pestaña «Cartera y CNC».
Para ver las bajas o el histórico, en el filtro lateral «Cartera» seleccioná
«Bajas durante 3M» o «Toda la cartera histórica 3M».

## Qué alerta muestra el principal

- Banner junto a los KPI: total de **clientes pendientes** y número de promotores con pendientes.
- Solapa `🔔 Seguimiento relevamientos`: **Asignados, relevados, pendientes, avance %** por promotor.
- Filtros de período, supervisor, promotor y negocio CZA/UNG.
- Tabla y descarga de **clientes que faltan relevar**, sin duplicar CZA + UNG.
- Actualización del aviso y panel cada 30 segundos; botón para forzar actualización.
- **Cartera y CNC** incorpora motivo, fecha y estado de la app de promotores, pero no los confunde con BEES Force.
- **Administrar campaña** permite recalcular e importar cartera desde el motor CNC para otro período.
  La acción se ejecuta solo si se confirma; usa el universo general, no una selección parcial.

**Criterios de cartera:** solo CNC U3M activos al cierre, con promotor asignado y tres meses de
antigüedad. CZA exige licencia alcohol `SI`; UNG no excluye por licencia.
Las respuestas de la app móvil **no son tareas BEES Force certificadas** ni visitas U12M.

## Conservar tu trabajo previo

Con ambos programas cerrados:

- Planes de acción del tablero CNC viejo: copiá su `CNC_DDV_LOCAL/data/cnc_local.sqlite`
  al mismo lugar dentro de `CNC_DDV_LOCAL/data/` del ZIP nuevo.
- Respuestas que ya guardaste en la app anterior: copiá su
  `CNC_Promotores_DDV/data/relevamientos.sqlite` a
  `datos_compartidos/relevamientos.sqlite` del ZIP nuevo.
- Si ya usaste una versión integrada anterior, copiá su
  `datos_compartidos/relevamientos.sqlite` al mismo lugar nuevo.
- **No reemplaces** la base nueva con una anterior después de comenzar a guardar respuestas.
  Copiá los archivos ANTES de abrir las aplicaciones.

La campaña de octubre se importa automáticamente solo cuando la base de respuestas está vacía.

## Para que funcione desde los celulares con un enlace

Las dos aplicaciones deben publicarse en servicios accesibles por Internet y tener **la misma
base de datos PostgreSQL persistente**, configurada en ambos Secrets:

`DATABASE_URL = "postgresql://USUARIO:CLAVE@HOST:5432/BASE?sslmode=require"`

El tablero principal también puede recibir `PROMOTORES_URL` para enlazar la app móvil.
La app del promotor exige códigos personales cuando `LOCAL_DEMO` no está activo.
**No publicar la base SQLite ni las ventas/clientes en un repositorio público.**
No alojar el panel administrativo públicamente sin controles de acceso.
Los archivos de negocio del tablero principal siguen requiriendo acceso a Google Drive.
Para probar los dos programas en un solo Windows no hay que configurar PostgreSQL.

## Diagnósticos

Si no arranca, enviá `CNC_DDV_LOCAL/diagnostico_inicio.txt` o una captura de la
consola de `CNC_Promotores_DDV`. Python 3.10 o posterior e Internet la primera vez
(para instalar bibliotecas). Los servidores deben permanecer abiertos mientras se usan.
