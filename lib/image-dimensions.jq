# Extract page dimensions when available
if (.page_id and .facsimile_width and .facsimile_height) then
  {
    page_id: .page_id,
    facsimile_width: .facsimile_width,
    facsimile_height: .facsimile_height
  }
else
  empty
end
