import { createRouter, createWebHistory } from "vue-router";
import OverviewView from "../views/OverviewView.vue";
import ServiceHealthView from "../views/ServiceHealthView.vue";
import TokenRouterView from "../views/TokenRouterView.vue";
import ApiManagementView from "../views/ApiManagementView.vue";
import RagInspectorView from "../views/RagInspectorView.vue";
import TraceViewerView from "../views/TraceViewerView.vue";
import AuditTrailView from "../views/AuditTrailView.vue";
import AlertsView from "../views/AlertsView.vue";

const routes = [
  { path: "/", name: "overview", component: OverviewView, meta: { title: "Overview" } },
  { path: "/health", name: "health", component: ServiceHealthView, meta: { title: "Service Health" } },
  { path: "/tokens", name: "tokens", component: TokenRouterView, meta: { title: "Token Router" } },
  { path: "/api", name: "api", component: ApiManagementView, meta: { title: "API Management" } },
  { path: "/rag", name: "rag", component: RagInspectorView, meta: { title: "RAG Inspector" } },
  { path: "/traces", name: "traces", component: TraceViewerView, meta: { title: "Trace Viewer" } },
  { path: "/audit", name: "audit", component: AuditTrailView, meta: { title: "Audit Trail" } },
  { path: "/alerts", name: "alerts", component: AlertsView, meta: { title: "Alerts & Drift" } },
];

const router = createRouter({
  history: createWebHistory("/obs/"),
  routes,
});

export default router;
