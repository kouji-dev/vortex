import { catalogModelByStoredModel, portalDefaultCatalogModel } from '~/hooks/useCatalogModelsQuery'
import type { CatalogModelEntry } from '~/lib/chat-types'

export function resolveSelectedCatalogModel(
  models: CatalogModelEntry[] | undefined,
  storedModel: string,
): CatalogModelEntry | null {
  if (storedModel.trim()) {
    return catalogModelByStoredModel(models, storedModel) ?? null
  }
  return portalDefaultCatalogModel(models)
}
