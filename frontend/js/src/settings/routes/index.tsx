import * as React from "react";
import { Navigate, type RouteObject } from "react-router";
import RouteLoader, { RouteQueryLoader } from "../../utils/Loader";
import ErrorBoundary from "../../error/ErrorBoundary";

const getSettingsRoutes = (): RouteObject[] => {
  const routes = [
    {
      path: "/settings",
      lazy: {
        Component: async () => {
          return (await import("../layout")).default;
        },
      },
      errorElement: <ErrorBoundary />,
      children: [
        {
          index: true,
          lazy: {
            Component: async () => {
              return (await import("../Settings")).default;
            },
          },
        },
        {
          path: "resettoken/",
          lazy: {
            Component: async () => {
              return (await import("../resettoken/ResetToken")).default;
            },
          },
        },
        {
          path: "music-services/details/",
          loader: RouteLoader,
          lazy: {
            Component: async () => {
              return (await import("../music-services/details/MusicServices")).default;
            },
          },
        },
        {
          path: "import/",
          loader: RouteLoader,
          lazy: {
            Component: async () => {
              return (await import("../import/ImportListens")).default;
            },
          },
        },
        {
          path: "brainzplayer/",
          lazy: {
            Component: async () => {
              return (await import("../brainzplayer/BrainzPlayerSettings")).default;
            },
          },
        },
        {
          path: "link-listens/",
          loader: RouteQueryLoader("link-listens"),
          lazy: {
            Component: async () => {
              return (await import("../link-listens/LinkListens")).default;
            },
          },
        },
        {
          path: "select_timezone/",
          loader: RouteLoader,
          lazy: {
            Component: async () => {
              return (await import("../select_timezone/SelectTimezone")).SelectTimezoneWrapper;
            },
          },
        },
        {
          path: "troi/",
          loader: RouteLoader,
          lazy: {
            Component: async () => {
              return (await import("../troi/SelectTroiPreferences")).SelectTroiPreferencesWrapper;
            },
          },
        },
        {
          path: "export/",
          lazy: {
            Component: async () => {
              return (await import("../export/ExportData")).default;
            },
          },
        },
        {
          path: "delete-listens/",
          lazy: {
            Component: async () => {
              return (await import("../delete-listens/DeleteListens")).default;
            },
          },
        },
        {
          path: "delete/",
          lazy: {
            Component: async () => {
              return (await import("../delete/DeleteAccount")).default;
            },
          },
        },
        {
          path: "import/",
          // Keep the /settings/import/ route for LastFM/LibreFM historical links,
          // and redirect to the music services page that replace those manual importers
          element: <Navigate to="../music-services/details/" replace />,
        },
      ],
    },
  ];
  return routes;
};

export default getSettingsRoutes;
