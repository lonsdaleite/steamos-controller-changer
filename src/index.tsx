import {
  definePlugin,
  PanelSection,
  PanelSectionRow,
  DropdownItem,
  SingleDropdownOption,
  staticClasses,
} from "@decky/ui";
import { callable, toaster } from "@decky/api";

const { useState, useEffect } = window.SP_REACT;
type VFC<P = {}> = (props: P) => JSX.Element | null;

type ControllerSelection = "default" | "legion_go_s" | "ps5_edge";

interface ControllerSettings {
  device_available: boolean;
  device_yaml_path: string;
  board_name: string;
  default_name: string;
  current_name: string;
  yaml_profile: ControllerSelection | "default" | "legion_go_s";
  active_controller: ControllerSelection;
  legion_go_s_name: string;
  ps5_edge_name: string;
  has_backup: boolean;
  last_error: string;
  running_as_root: boolean;
  effective_uid: number;
  plugin_version: string;
}

const getControllerSettings = callable<[], ControllerSettings>(
  "get_controller_settings"
);
const setController = callable<[ControllerSelection], boolean>("set_controller");

const PLUGIN_TITLE = "Controller Changer";

const selectionLabel = (
  selection: ControllerSelection,
  settings: ControllerSettings
): string => {
  switch (selection) {
    case "legion_go_s":
      return settings.legion_go_s_name;
    case "ps5_edge":
      return settings.ps5_edge_name;
    default:
      return settings.default_name;
  }
};

const ControllerChangerContent: VFC = () => {
  const [settings, setSettings] = useState<ControllerSettings | null>(null);
  const [selected, setSelected] = useState<ControllerSelection>("default");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const refreshSettings = async () => {
    try {
      const data = await getControllerSettings();
      setSettings(data);
      setSelected(data.active_controller);
      setErrorMessage(data.last_error || "");
    } catch (e) {
      console.error("Failed to get controller settings:", e);
      setErrorMessage(`Failed to load settings: ${String(e)}`);
    }
  };

  useEffect(() => {
    const load = async () => {
      await refreshSettings();
      setLoading(false);
    };
    load();
  }, []);

  const buildOptions = (
    data: ControllerSettings
  ): SingleDropdownOption[] => [
    {
      data: "default" as ControllerSelection,
      label: `${data.default_name} (Default)`,
    },
    {
      data: "legion_go_s" as ControllerSelection,
      label: data.legion_go_s_name,
    },
    {
      data: "ps5_edge" as ControllerSelection,
      label: data.ps5_edge_name,
    },
  ];

  const handleControllerChange = async (option: SingleDropdownOption) => {
    const next = option.data as ControllerSelection;
    if (next === selected || busy) {
      return;
    }

    const previous = selected;
    setSelected(next);
    setBusy(true);
    setErrorMessage("");

    try {
      const success = await setController(next);
      await refreshSettings();

      if (success) {
        const latest = await getControllerSettings();
        toaster.toast({
          title: PLUGIN_TITLE,
          body: `Switched to ${selectionLabel(next, latest)}`,
        });
      } else {
        setSelected(previous);
        const latest = await getControllerSettings();
        setErrorMessage(
          latest.last_error || "Failed to switch controller profile"
        );
        toaster.toast({
          title: PLUGIN_TITLE,
          body: latest.last_error || "Failed to switch controller profile",
        });
      }
    } catch (e) {
      setSelected(previous);
      const message = `Failed to switch controller: ${String(e)}`;
      setErrorMessage(message);
      toaster.toast({
        title: PLUGIN_TITLE,
        body: message,
      });
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <PanelSection title="Controller">
        <PanelSectionRow>
          <div style={{ color: "#8b929a" }}>Loading...</div>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  if (!settings?.device_available) {
    return (
      <PanelSection title="Controller">
        <PanelSectionRow>
          <div style={{ color: "#8b929a" }}>
            No InputPlumber device profile found for this board
            {settings?.board_name ? ` (${settings.board_name})` : ""}.
          </div>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <PanelSection title="Controller">
      <PanelSectionRow>
        <DropdownItem
          label="Controller Profile"
          description="Switch InputPlumber device profile and emulation target"
          layout="below"
          childrenContainerWidth="max"
          rgOptions={buildOptions(settings)}
          selectedOption={selected}
          disabled={busy || !settings.running_as_root}
          onChange={handleControllerChange}
        />
      </PanelSectionRow>

      {!settings.running_as_root && (
        <PanelSectionRow>
          <div style={{ color: "#b8860b", fontSize: "12px" }}>
            Root access is required. Run: sudo systemctl restart plugin_loader
          </div>
        </PanelSectionRow>
      )}

      {busy && (
        <PanelSectionRow>
          <div style={{ color: "#8b929a", fontSize: "12px" }}>
            Applying controller profile...
          </div>
        </PanelSectionRow>
      )}

      {errorMessage && (
        <PanelSectionRow>
          <div
            style={{
              color: "#ff6b6b",
              fontSize: "12px",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {errorMessage}
          </div>
        </PanelSectionRow>
      )}

      <PanelSectionRow>
        <div style={{ color: "#8b929a", fontSize: "11px" }}>
          v{settings.plugin_version} | uid={settings.effective_uid} | yaml=
          {settings.yaml_profile} | selected={settings.active_controller} |
          backup={settings.has_backup ? "yes" : "no"}
        </div>
      </PanelSectionRow>
    </PanelSection>
  );
};

const ControllerChangerIcon: VFC = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" width="1em" height="1em">
    <path d="M6 11h2v2H6v-2zm4 0h2v2h-2v-2zm4 0h2v2h-2v-2zm-6 4h2v2h-2v-2zm4 0h2v2h-2v-2zM4 8h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2zm0 2v8h16v-8H4z" />
  </svg>
);

export default definePlugin(() => {
  return {
    name: PLUGIN_TITLE,
    title: <div className={staticClasses.Title}>{PLUGIN_TITLE}</div>,
    content: <ControllerChangerContent />,
    icon: <ControllerChangerIcon />,
  };
});
