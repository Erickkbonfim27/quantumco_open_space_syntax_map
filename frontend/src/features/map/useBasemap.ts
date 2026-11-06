import { useCallback, useState } from "react";

import { useSession } from "../../lib/session";
import { BASEMAPS, type BasemapId, saveBasemap, savedBasemap } from "./basemapStyle";

const known = (id: string | undefined): id is BasemapId => BASEMAPS.some((b) => b.id === id);

/** Fundo escolhido: do perfil (se logado), senão do navegador; o padrão segue o tema. */
export function useBasemap(): [BasemapId, (id: BasemapId) => void] {
  const { user, savePreferences } = useSession();
  const fromProfile = user?.preferences.basemap;
  const [local, setLocal] = useState<BasemapId>(savedBasemap);
  const basemap = known(fromProfile) ? fromProfile : local;
  const set = useCallback(
    (id: BasemapId) => {
      saveBasemap(id);
      setLocal(id);
      savePreferences({ basemap: id });
    },
    [savePreferences],
  );
  return [basemap, set];
}
