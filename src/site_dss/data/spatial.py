"""Screening results; geometric intersection alone is not legal exclusion."""
from shapely.geometry import shape
from pyproj import Geod

def screen(site,restrictions):
    g=shape(site.geometry);hits=[]
    for item in restrictions:
        r=shape(item['geometry'])
        if not r.is_valid or r.is_empty:raise ValueError('invalid restriction geometry')
        if g.intersects(r):hits.append(dict(restriction_id=item['restriction_id'],evidence_id=item['evidence_id'],requires_expert_review=True))
    return dict(site_id=site.site_id,crs='EPSG:4326',area_m2=abs(Geod(ellps='WGS84').geometry_area_perimeter(g)[0]),intersections=hits,synthetic_map_only=True)
