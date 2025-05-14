import streamlit as st
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import box, Polygon
from matplotlib_scalebar.scalebar import ScaleBar
from pathlib import Path
import tempfile
import zipfile
import folium
from matplotlib.patches import ConnectionPatch, Rectangle
import matplotlib.image as mpimg
from io import BytesIO
import base64
import numpy as np
from matplotlib.ticker import AutoMinorLocator
import os
import contextily as ctx

# Set page config
st.set_page_config(layout="wide")
st.title("🌍 Professional Map Generator")

def dd_to_dms(dd, latlon):
    direction = ""
    if latlon == "lat":
        direction = "N" if dd >= 0 else "S"
    elif latlon == "lon":
        direction = "E" if dd >= 0 else "W"
    
    dd = abs(dd)
    degrees = int(dd)
    minutes = int((dd - degrees) * 60)
    seconds = (dd - degrees - minutes/60) * 3600
    
    return f"{degrees}°{minutes}'{seconds:.2f}\"{direction}"

def get_image_download_link(fig, filename="map.png", text="Download PNG"):
    buff = BytesIO()
    fig.savefig(buff, format='png', dpi=300, bbox_inches='tight')
    buff.seek(0)
    img_str = base64.b64encode(buff.read()).decode()
    href = f'<a href="data:image/png;base64,{img_str}" download="{filename}" style="text-decoration: none;"><button style="background-color: #4CAF50; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer;">{text}</button></a>'
    return href

def get_html_download_link(m, filename="map.html", text="Download HTML"):
    html = m.get_root().render()
    b64 = base64.b64encode(html.encode()).decode()
    href = f'<a href="data:text/html;base64,{b64}" download="{filename}" style="text-decoration: none;"><button style="background-color: #008CBA; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer;">{text}</button></a>'
    return href

def set_plot_style():
    plt.style.use('default')
    plt.rcParams.update({
        'axes.facecolor': '#f8f9fa',
        'axes.edgecolor': '#2c3e50',
        'axes.grid': True,
        'grid.color': 'white',
        'grid.linewidth': 0.5,
        'figure.facecolor': 'white',
        'font.family': 'sans-serif'
    })

set_plot_style()

@st.cache_resource
def load_world():
    zip_path = Path("data/ne_110m_admin_0_countries.zip")
    extract_dir = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)
    for shp in extract_dir.glob("**/*.shp"):
        return gpd.read_file(shp).to_crs("EPSG:4326")
    return gpd.GeoDataFrame()

world = load_world()

left, right = st.columns([1, 2])

with left:
    country_list = sorted(world['ADMIN'].unique())
    selected_country = st.selectbox("Select Country", country_list, index=country_list.index("Kenya") if "Kenya" in country_list else 0)
    country_geom = world[world['ADMIN'] == selected_country]

    study_method = st.radio("Define Study Area By:", ["Upload Shapefile ZIP", "Paste Coordinates"], index=0)
    polygon = None
    selection = None
    admin_col = None
    site_labels = []
    site_area_name = st.text_input("Name of Study Area (for label)", "Study Area")
    gdf = None

    if study_method == "Upload Shapefile ZIP":
        uploaded_zip = st.file_uploader("Upload ZIP with Shapefiles", type="zip")

        def extract_shapefiles(zip_file):
            extract_path = Path(tempfile.mkdtemp())
            with zipfile.ZipFile(zip_file) as z:
                z.extractall(extract_path)
            
            shapefiles = []
            for root, dirs, files in os.walk(extract_path):
                for file in files:
                    if file.lower().endswith('.shp'):
                        full_path = Path(root) / file
                        base_name = full_path.stem
                        parent_dir = full_path.parent
                        
                        required_exts = ['.shp', '.dbf', '.shx']
                        has_all_files = all((parent_dir / f"{base_name}{ext}").exists() for ext in required_exts)
                        
                        if has_all_files:
                            shapefiles.append(full_path)
            
            return shapefiles

        shapefile_paths = []
        if uploaded_zip:
            shapefile_paths = extract_shapefiles(uploaded_zip)
            if not shapefile_paths:
                st.error("""
                No valid shapefiles found. Please ensure:
                1. ZIP contains .shp files
                2. Each .shp has matching .dbf and .shx files
                3. All files have same base name (e.g., 'file.shp', 'file.dbf', 'file.shx')
                """)
            else:
                shapefile_names = [str(f.relative_to(f.parent)) for f in shapefile_paths]
                selected_shp = st.selectbox("Select shapefile:", shapefile_names)
                selected_path = shapefile_paths[shapefile_names.index(selected_shp)]
                try:
                    gdf = gpd.read_file(selected_path).to_crs("EPSG:4326")
                    st.success(f"Loaded: {selected_shp}")
                except Exception as e:
                    st.error(f"Error loading shapefile: {str(e)}")

    elif study_method == "Paste Coordinates":
        coord_input = st.text_area("Paste Coordinates (lat, lon per line)")
        site_label_prefix = st.text_input("Site Label Prefix", value="Site")
        show_site_labels = st.checkbox("Show Site Labels on Map", value=True)
        if coord_input.strip():
            try:
                coords = [tuple(map(float, line.split(","))) for line in coord_input.strip().splitlines()]
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                poly_geom = Polygon([(lon, lat) for lat, lon in coords])
                polygon = gpd.GeoDataFrame(geometry=[poly_geom], crs="EPSG:4326")
                selection = polygon
                site_labels = [(f"{site_label_prefix} {i+1}", coords[i]) for i in range(len(coords)-1)]
                
                st.markdown("**Coordinates in DMS Format:**")
                for i, (lat, lon) in enumerate(coords[:-1]):
                    st.write(f"{site_label_prefix} {i+1}: {dd_to_dms(lat, 'lat')}, {dd_to_dms(lon, 'lon')}")
            except Exception as e:
                st.error(f"Invalid coordinates: {e}")

    if gdf is not None:
        admin_col = st.selectbox("Choose Area Name Column", gdf.columns.tolist())
        selected_areas = st.multiselect("Select Area(s)", gdf[admin_col].unique().tolist())
        if selected_areas:
            selection = gdf[gdf[admin_col].isin(selected_areas)]

    st.markdown("### Optional Layers")
    extra_layers = st.file_uploader("Upload GeoJSON layers", type="geojson", accept_multiple_files=True)
    extra_gdfs = []
    if extra_layers:
        for layer in extra_layers:
            try:
                gdf_layer = gpd.read_file(layer).to_crs("EPSG:4326")
                extra_gdfs.append((layer.name, gdf_layer))
            except:
                st.warning(f"Could not load: {layer.name}")

with right:
    if selection is not None and not selection.empty:
        show_polygon = st.checkbox("Show Coordinate Polygon", value=True)
        show_labels = st.checkbox("Show Region Labels", value=True)
        show_country_label = st.checkbox("Show Country Name", value=True)
        show_basemap = st.checkbox("Show Basemap", value=False)
        basemap_provider = st.selectbox("Basemap Style", 
                                      ["OpenStreetMap", "Stamen Terrain", "Stamen Toner", "Esri WorldImagery"],
                                      index=0) if show_basemap else None
        map_title = st.text_input("Map Title", f"Study Area in {selected_country}")

        fig = plt.figure(figsize=(14, 12.5), facecolor='white')
        fig.suptitle(map_title, fontsize=18, fontweight='bold', y=0.97)
        
        ax_main = fig.add_axes([0.05, 0.2, 0.7, 0.7])
        ax_main.set_facecolor('#f8f9fa')
        
        ax_inset = fig.add_axes([0.75, 0.72, 0.22, 0.25])
        ax_inset.set_facecolor('#f8f9fa')

        # Plot with or without basemap
        if show_basemap:
            selection.plot(ax=ax_main, edgecolor="#2c3e50", facecolor="#3498db80", 
                         linewidth=1.5, label="Study Area", alpha=0.7)
            try:
                if basemap_provider == "OpenStreetMap":
                    ctx.add_basemap(ax_main, crs=selection.crs.to_string(), source=ctx.providers.OpenStreetMap.Mapnik)
                elif basemap_provider == "Stamen Terrain":
                    ctx.add_basemap(ax_main, crs=selection.crs.to_string(), source=ctx.providers.Stamen.Terrain)
                elif basemap_provider == "Stamen Toner":
                    ctx.add_basemap(ax_main, crs=selection.crs.to_string(), source=ctx.providers.Stamen.Toner)
                elif basemap_provider == "Esri WorldImagery":
                    ctx.add_basemap(ax_main, crs=selection.crs.to_string(), source=ctx.providers.Esri.WorldImagery)
            except Exception as e:
                st.warning(f"Could not load basemap: {str(e)}")
        else:
            selection.plot(ax=ax_main, edgecolor="#2c3e50", facecolor="#3498db", 
                         linewidth=1.5, label="Study Area")

        legend_elements = [
            plt.Line2D([0], [0], color='#3498db', lw=2, label='Study Area'),
            plt.Line2D([0], [0], marker='o', color='#e74c3c', label='Site Points', markersize=6)
        ]

        if show_basemap:
            legend_elements.append(
                plt.Line2D([0], [0], color=(0,0,0,0), marker='s', 
                markersize=10, markerfacecolor='lightgray',
                label=f'{basemap_provider} Basemap')
            )

        if not selection.empty:
            centroid = selection.geometry.centroid.iloc[0]
            ax_main.text(centroid.x, centroid.y, site_area_name, 
                        fontsize=12, ha='center', va='center',
                        color='white', weight='bold',
                        bbox=dict(facecolor='#2c3e50', alpha=0.8, boxstyle='round,pad=0.3'))

        if admin_col and show_labels:
            for idx, row in selection.iterrows():
                if row.geometry.geom_type == 'Polygon':
                    x, y = row.geometry.centroid.coords[0]
                    ax_main.text(x, y, str(row[admin_col]), 
                               fontsize=9, ha='center', va='center',
                               bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.2'))

        if show_polygon and polygon is not None:
            polygon.plot(ax=ax_main, edgecolor="#e74c3c", facecolor="none", linewidth=1.5, linestyle='--', label="Boundary")
            legend_elements.append(plt.Line2D([0], [0], color='#e74c3c', linestyle='--', lw=1.5, label='Boundary'))
            
            if show_site_labels:
                for name, (lat, lon) in site_labels:
                    ax_main.plot(lon, lat, marker='o', color='#e74c3c', markersize=6)
                    ax_main.text(lon, lat, name, fontsize=8, ha='left', va='bottom', 
                               color='darkred', bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.2'))

        for name, gdf in extra_gdfs:
            color = '#27ae60'
            gdf.plot(ax=ax_main, color=color, linewidth=1)
            legend_elements.append(plt.Line2D([0], [0], color=color, lw=1, label=name))

        scalebar = ScaleBar(100000, units="m", location='lower left', 
                          border_pad=0.5, scale_loc='bottom', 
                          color='#2c3e50', box_color='white', box_alpha=0.7)
        ax_main.add_artist(scalebar)

        # North Arrow in Top-Left Corner
        ax_main.annotate('N', xy=(0.05, 0.95), xytext=(0.05, 0.90),
                        xycoords='axes fraction',
                        arrowprops=dict(arrowstyle='->', linewidth=1.5, color='#2c3e50'),
                        fontsize=12, ha='center', va='center', color='#2c3e50',
                        bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.2'))

        country_geom.plot(ax=ax_inset, color="#bdc3c7", edgecolor="#7f8c8d", linewidth=0.5)
        bounds = selection.total_bounds
        box_geom = box(*bounds)
        gpd.GeoSeries([box_geom], crs="EPSG:4326").plot(ax=ax_inset, edgecolor="#e74c3c", facecolor="none", linewidth=1.5)

        if show_country_label:
            cx, cy = country_geom.geometry.centroid.iloc[0].coords[0]
            ax_inset.text(cx, cy, selected_country, fontsize=10, ha='center', 
                         color='#2c3e50', weight='bold',
                         bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.3'))

        if selection.geometry.geom_type.iloc[0] == 'Polygon':
            poly_vertices = list(selection.geometry.iloc[0].exterior.coords)
            if len(poly_vertices) >= 4:
                arrow_points = [poly_vertices[0], poly_vertices[len(poly_vertices)//2]]
                
                def data_to_axes(data_x, data_y, ax):
                    x_range = ax.get_xlim()[1] - ax.get_xlim()[0]
                    y_range = ax.get_ylim()[1] - ax.get_ylim()[0]
                    return ((data_x - ax.get_xlim()[0]) / x_range, 
                            (data_y - ax.get_ylim()[0]) / y_range)
                
                if len(arrow_points) == 2:
                    main_p1 = data_to_axes(arrow_points[0][0], arrow_points[0][1], ax_main)
                    main_p2 = data_to_axes(arrow_points[1][0], arrow_points[1][1], ax_main)
                    inset_p1 = data_to_axes(arrow_points[0][0], arrow_points[0][1], ax_inset)
                    inset_p2 = data_to_axes(arrow_points[1][0], arrow_points[1][1], ax_inset)
                    
                    con1 = ConnectionPatch(
                        xyA=inset_p1, xyB=main_p1,
                        coordsA="axes fraction", coordsB="axes fraction",
                        axesA=ax_inset, axesB=ax_main,
                        arrowstyle="->", color="#2c3e50", linewidth=1.5,
                        connectionstyle="arc3,rad=0"
                    )
                    con2 = ConnectionPatch(
                        xyA=inset_p2, xyB=main_p2,
                        coordsA="axes fraction", coordsB="axes fraction",
                        axesA=ax_inset, axesB=ax_main,
                        arrowstyle="->", color="#2c3e50", linewidth=1.5,
                        connectionstyle="arc3,rad=0"
                    )
                    fig.add_artist(con1)
                    fig.add_artist(con2)

        ax_main.tick_params(axis='both', which='major', labelsize=8)
        ax_main.set_xlabel("Longitude", fontsize=9, labelpad=5)
        ax_main.set_ylabel("Latitude", fontsize=9, labelpad=15)
        
        ax_main.xaxis.set_minor_locator(AutoMinorLocator())
        ax_main.yaxis.set_minor_locator(AutoMinorLocator())
        ax_main.grid(which='minor', linestyle=':', linewidth=0.5, color='gray')

        fig.patches.append(Rectangle((0.02, 0.02), 0.96, 0.96, transform=fig.transFigure,
                                   fill=False, edgecolor='#2c3e50', linewidth=2, zorder=10))

        logo_path = Path("data/logo.png")
        if logo_path.exists():
            try:
                logo_img = mpimg.imread(str(logo_path))
                logo_ax = fig.add_axes([0.05, 0.88, 0.1, 0.1], anchor='NW')
                logo_ax.imshow(logo_img)
                logo_ax.axis('off')
            except:
                pass

        legend = ax_main.legend(handles=legend_elements, loc='lower right',
                              frameon=True, framealpha=0.9,
                              facecolor='white', edgecolor='#2c3e50',
                              title='Map Legend', title_fontsize=10)
        legend.get_frame().set_linewidth(1.5)

        plt.tight_layout(pad=2.5)
        fig.subplots_adjust(left=0.12, right=0.88, top=0.92, bottom=0.12)

        st.pyplot(fig)

        st.markdown("---")
        st.markdown("""
        <div style="text-align: center; margin-top: 20px;">
            <h4>Professional Geospatial Mapping Tool</h4>
            <p>Developed by Basil Kaudo | okothbasil45@gmail.com | © 2025</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### Download Options")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(get_image_download_link(fig), unsafe_allow_html=True)
        
        with col2:
            try:
                m = folium.Map(location=[selection.geometry.centroid.y.mean(), 
                                        selection.geometry.centroid.x.mean()], 
                              zoom_start=10)
                
                tooltip_fields = [admin_col] if admin_col else []
                popup_fields = [admin_col] if admin_col else []
                
                folium.GeoJson(
                    selection,
                    style_function=lambda feature: {
                        'fillColor': '#3498db',
                        'color': '#2c3e50',
                        'weight': 1.5,
                        'fillOpacity': 0.7
                    },
                    tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_fields),
                    popup=folium.GeoJsonPopup(fields=popup_fields)
                ).add_to(m)
                
                folium.GeoJson(
                    country_geom,
                    style_function=lambda feature: {
                        'fillColor': '#bdc3c7',
                        'color': '#7f8c8d',
                        'weight': 0.5,
                        'fillOpacity': 0.5
                    }
                ).add_to(m)
                
                if study_method == "Paste Coordinates":
                    for name, (lat, lon) in site_labels:
                        folium.Marker(
                            [lat, lon],
                            popup=f"{name}<br>Lat: {dd_to_dms(lat, 'lat')}<br>Lon: {dd_to_dms(lon, 'lon')}",
                            icon=folium.Icon(color='red', icon='info-sign')
                        ).add_to(m)
                
                st.markdown(get_html_download_link(m), unsafe_allow_html=True)
            except Exception as e:
                st.warning(f"Could not generate interactive map: {str(e)}")
                st.markdown("HTML download not available", unsafe_allow_html=True)
