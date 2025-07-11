# aggregator
if (.out_of_bounds_lines | length == 0) and 
   (.out_of_bounds_paragraphs | length == 0) and 
   (.out_of_bounds_regions | length == 0) then
  {}
else
  {
    page_id: .page_id,
    bad_lines_count: (.out_of_bounds_lines | length),
    bad_paragraphs_count: (.out_of_bounds_paragraphs | length),
    bad_regions_count: (.out_of_bounds_regions | length),
    cc: .cc
  }
end
