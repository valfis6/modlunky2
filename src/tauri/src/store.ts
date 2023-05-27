import type { Writable } from "svelte/store";
import { derived, writable } from "svelte/store";

export const theme = writable("dark");

export const activeTabIndex = writable(0);

let id_counter = 0;
export const mods: Writable<Mod[]> = writable([
  {
    name: "Backpack",
    enabled: true,
    id: id_counter++,
  },
  {
    name: "Tele-trainer",
    enabled: true,
    id: id_counter++,
  },
  {
    name: "Randomizer",
    enabled: false,
    id: id_counter++,
  },
]);

export const enabledMods: Writable<Mod[]> = writable([]);
mods.subscribe((mods) => {
  // Update enabled mods without changing order
  enabledMods.update((enabledMods) => {
    const newEnabledMods = mods.filter((mod) => mod.enabled);
    // Update enabled mods references and add new enabled mods
    for (let newEnabledMod of newEnabledMods) {
      let enabledModIndex = enabledMods.findIndex(
        (enabledMod) => enabledMod.id === newEnabledMod.id
      );

      if (enabledModIndex !== -1) {
        enabledMods[enabledModIndex] = newEnabledMod;
      } else if (newEnabledMod.enabled) {
        enabledMods.push(newEnabledMod);
      }
    }
    // Remove disabled or no longer existant mods
    return enabledMods.filter((mod) => newEnabledMods.includes(mod));
  });
});

export const installedMods = derived(mods, ($mods) =>
  $mods.filter((mod) => !mod.enabled)
);

export function toggleMod(id: number) {
  mods.update((arr) =>
    arr.map((mod) => (mod.id === id ? { ...mod, enabled: !mod.enabled } : mod))
  );
}

export const searchInput = writable("");

function search(mod: Mod, query: string) {
  return mod.name && mod.name.toLowerCase().includes(query.toLowerCase());
}

export const filteredEnabledMods = derived(
  [enabledMods, searchInput],
  ([$enabledMods, $searchInput]) =>
    $enabledMods.filter((mod) => search(mod, $searchInput))
);
export const filteredInstalledMods = derived(
  [installedMods, searchInput],
  ([$installedMods, $searchInput]) =>
    $installedMods.filter((mod) => search(mod, $searchInput))
);

id_counter = 0;
export const versions = [
  {
    revision: "v0.12.0",
    installed: true,
    id: id_counter++,
  },
  {
    revision: "v0.11.1",
    installed: true,
    id: id_counter++,
  },
  {
    revision: "v0.11.0",
    installed: true,
    id: id_counter++,
  },
  {
    revision: "v0.10.1",
    installed: false,
    id: id_counter++,
  },
  {
    revision: "v0.10.0",
    installed: false,
    id: id_counter++,
  },
];
export const version = writable(versions[0]);

export const colorKey = writable("#ff00ff");
