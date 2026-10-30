/**
 * The ECharts runtime the spend chart needs, tree-shaken from echarts/core (bar series, grid,
 * tooltip, canvas renderer). Imported on demand in the browser only.
 */
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

export { init };
