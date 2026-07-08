import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: Index,
});

function Index() {
  if (typeof window !== "undefined") {
    window.location.replace("/index.html");
  }
  return null;
}
