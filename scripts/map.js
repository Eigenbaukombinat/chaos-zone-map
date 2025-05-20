function initMap(map) {
  addImages(map);
  addDetailsPopup(map);

  fetch("./spaceapi").then((res) => {
    res.json().then((spaces) => displaySpacesLayer(spaces, map));
  });
}

async function addImages(map) {
  map
    .loadImage("./static/marker_small_white.png?l=1")
    .then((image) => map.addImage("custom-marker", image.data));
  map
    .loadImage("./static/marker_small_green.png?l=1")
    .then((image) => map.addImage("custom-marker-green", image.data));
    map
      .loadImage("./static/marker_cluster.png?l=1")
      .then((image) => map.addImage("custom-marker-cluster", image.data));
}

async function displaySpacesLayer(spaces, map) {
  const spaceFeatures = [];
  const bounds = new maplibregl.LngLatBounds();

  spaces.forEach((space) => {
    if (
      !space.data ||
      !space.data.ext_habitat ||
      space.data.ext_habitat.toLowerCase() != "chaoszone"
    ) {
      return;
    }

    const open = space.data.state && space.data.state.open;

    spaceFeatures.push({
      type: "Feature",
      properties: {
        space: space.data,
        icon: "custom-marker" + (open ? "-green" : ""),
      },
      geometry: {
        type: "Point",
        coordinates: [space.data.location.lon, space.data.location.lat],
      },
    });

    console.log(space);
    bounds.extend(
      new maplibregl.LngLat(space.data.location.lon, space.data.location.lat)
    );
  });

  map.addSource("points", {
    type: "geojson",
    data: {
      type: "FeatureCollection",
      features: spaceFeatures,
    },
    cluster: true,
    clusterMaxZoom: 12, // Max zoom to cluster points on
    clusterRadius: 26, // Radius of each cluster when clustering points (defaults to 50)
  });

  // Add a symbol layer
  map.addLayer({
    id: "symbols",
    type: "symbol",
    source: "points",
    filter: ["!", ["has", "point_count"]],
    layout: {
      "icon-image": "{icon}",
      "icon-size": 0.4,
      "icon-allow-overlap": true,
    },
  });

  map.addLayer({
    id: "clusters",
    type: "symbol",
    source: "points",
    filter: ["has", "point_count"],
    layout: {
      "icon-image": "custom-marker-cluster",
      "icon-size": 0.4,
      "icon-allow-overlap": true,
    },
  });

  map.addLayer({
    id: "cluster-count",
    type: "symbol",
    source: "points",
    filter: ["has", "point_count"],
    layout: {
      "text-field": "{point_count_abbreviated}",
      "text-font": ["Noto Sans Bold"],
      "text-size": 24,
      "text-allow-overlap": true,
    },
    paint: {
      "text-color": "rgba(255, 255, 255, 1)",
    },
  });

  map.fitBounds(bounds, { padding: 100, animate: false });

  map.getCanvas().style.cursor = "default";
}

function addDetailsPopup(map) {
  map.on("mouseenter", "symbols", () => {
    map.getCanvas().style.cursor = "pointer";
  });

  map.on("mouseleave", "symbols", () => {
    map.getCanvas().style.cursor = "default";
  });

  map.on("mouseenter", "clusters", () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "clusters", () => {
    map.getCanvas().style.cursor = "default";
  });

  map.on("click", "symbols", (e) => {
    const coordinates = e.features[0].geometry.coordinates.slice();
    const space = JSON.parse(e.features[0].properties.space);
    console.log(e.features[0]);

    // Ensure that if the map is zoomed out such that multiple
    // copies of the feature are visible, the popup appears
    // over the copy being pointed to.
    while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
      coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360;
    }

    const open = space.state && space.state.open;

    let stateHtml = space.state
      ? `<div>${open ? "geöffnet" : "gerade geschlossen"}</div>`
      : "";

    let html = `<div>
              <div><strong>${space.space}</strong></div>
              ${stateHtml}
              <div><a href="${space.url}" target='_blank'>${space.url}</a></div>
            </div>`;

    new maplibregl.Popup().setLngLat(coordinates).setHTML(html).addTo(map);
  });

  map.on("click", "clusters", async (e) => {
    const features = map.queryRenderedFeatures(e.point, {
      layers: ["clusters"],
    });

    const clusterId = features[0].properties.cluster_id;

    const zoom = await map
      .getSource("points")
      .getClusterExpansionZoom(clusterId);

    map.easeTo({
      center: features[0].geometry.coordinates,
      zoom,
    });
  });
}
