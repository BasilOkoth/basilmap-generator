
# Basil's GeoMap Tool

**Developed by Basil Kaudo**  
_A geospatial research and planning tool for both single and multi-area study mapping._

## Features
- Select one or more countries to highlight
- Define study areas using:
    - Coordinates (lat, lon)
    - Shapefiles (zipped) or GeoJSON
- Add up to 5 thematic layers
- Export:
    - Interactive HTML map
    - High-resolution PNG with:
        - North arrow
        - Scalebar
        - Labels
        - Project branding

## How to Run

### 1. Install requirements
```bash
pip install streamlit geopandas matplotlib shapely streamlit-folium matplotlib-scalebar pandas
```

### 2. Launch the tool
```bash
streamlit run enhanced_multi_area_map_app.py
```

### 3. PNG Export
- Optionally generate a PNG with official formatting.
- Works for both single and multi-area maps.

## Notes
- For shapefiles, upload as a ZIP containing `.shp`, `.dbf`, `.shx`, and `.prj`.
- Coordinate input accepts multiple lines: `lat, lon` per line.

## Contact
Developed by **Basil Kaudo**
