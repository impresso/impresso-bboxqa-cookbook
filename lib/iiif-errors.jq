# Filter for entries with "error" at the top level and return "page_id" and "iiif_manifest"
if .error then
  {
    page_id: .page_id,
    error: .error,
    iiif_base_uri:.iiif_manifest.iiif_base_uri
  }
else
  {}
end
