// frontend/src/App.js

import React, { useState, useEffect, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Tooltip } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import ReactDOMServer from 'react-dom/server';
import ForecastChart from './ForecastChart'; // Import the new component

// --- Configuration ---
const API_BASE_URL = 'http://127.0.0.1:8000'; // Make sure this matches your FastAPI server
const MAP_CENTER = [20, 10]; // Initial map center
const MAP_ZOOM = 2; // Initial map zoom level
const EVENT_TYPES = [
    'Labor_Issue', 'Logistics_Issue', 'Natural_Disaster',
    'Industrial_Accident', 'Political_Regulatory', 'Demand_Supply_Shift',
    'Cyber_Attack'
];

// --- Custom SVG Icon Creation ---
// Creates a custom SVG icon for Leaflet markers based on class and optional text
const createSvgIcon = (className, text = '') => {
    const html = ReactDOMServer.renderToString(
        <div className={`svg-marker ${className}`}>
            {text}
        </div>
    );
    return L.divIcon({
        html: html,
        className: 'custom-div-icon', // General class for all custom divIcons
        iconSize: [30, 30], // Increased size for better visibility
        iconAnchor: [15, 15], // Center the icon
        popupAnchor: [0, -15] // Position popup correctly above the marker
    });
};

// Determines the icon for CURRENT events based on impact score
const getEventImpactIcon = (impactScore) => {
    if (impactScore === null || impactScore === undefined) return createSvgIcon('impact-low', '!');
    if (impactScore >= 30) return createSvgIcon('impact-critical', '🚨'); // Critical (e.g., 5*8=40, 5*7=35)
    if (impactScore >= 15) return createSvgIcon('impact-high', '!');    // High (e.g., 3*8=24, 4*4=16)
    if (impactScore >= 5) return createSvgIcon('impact-medium', '-');  // Medium (e.g., 2*3=6, 1*5=5)
    return createSvgIcon('impact-low', '✔️');                         // Low
};

// Determines the icon for FORECASTED/PREDICTED events
const getForecastedEventIcon = (impactScore, confidence) => {
    // Use different styling for forecasted events (outlined/hollow style)
    const baseClass = confidence === 'high' ? 'forecasted-high' : 
                     confidence === 'medium' ? 'forecasted-medium' : 'forecasted-low';
    
    if (impactScore === null || impactScore === undefined) return createSvgIcon(`${baseClass} forecasted-marker`, '🔮');
    if (impactScore >= 30) return createSvgIcon(`${baseClass} forecasted-marker forecasted-critical`, '⚠️');
    if (impactScore >= 15) return createSvgIcon(`${baseClass} forecasted-marker`, '⚠️');
    if (impactScore >= 5) return createSvgIcon(`${baseClass} forecasted-marker`, '🔮');
    return createSvgIcon(`${baseClass} forecasted-marker`, '○');
};

// Determines the CSS class for an event based on its impact score for styling list items
const getImpactClass = (impactScore) => {
    if (impactScore === null || impactScore === undefined) return 'impact-low';
    if (impactScore >= 30) return 'impact-critical';
    if (impactScore >= 15) return 'impact-high';
    if (impactScore >= 5) return 'impact-medium';
    return 'impact-low';
};

// Icon for supplier nodes
const getSupplierIcon = (criticality) => {
    let className = 'supplier-marker';
    let text = 'S';
    if (criticality >= 4) className += ' supplier-critical'; // Highlight highly critical suppliers
    else if (criticality >= 2) className += ' supplier-medium';
    return createSvgIcon(className, text);
};


// --- Main App Component ---
function App() {
    // --- State Management ---
    const [suppliers, setSuppliers] = useState([]);
    const [displayedEvents, setDisplayedEvents] = useState([]);
    const [forecastedEvents, setForecastedEvents] = useState([]);
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    
    // Filter States
    const [selectedNode, setSelectedNode] = useState('');
    const [selectedEventType, setSelectedEventType] = useState('');
    const [showCurrentEvents, setShowCurrentEvents] = useState(true);
    const [showForecastedEvents, setShowForecastedEvents] = useState(true);

    // --- Data Fetching Logic ---
    const fetchEvents = useCallback(async () => {
        try {
            setLoading(true);
            setError(null); // Clear previous errors
            
            // Fetch current events
            let currentUrl = `${API_BASE_URL}/events/latest?count=100`;
            let forecastedUrl = `${API_BASE_URL}/events/forecasted?count=100`;
            
            if (selectedNode) {
                currentUrl = `${API_BASE_URL}/events/by_node/${selectedNode}?limit=100`;
                forecastedUrl = `${API_BASE_URL}/events/forecasted/by_node/${selectedNode}?limit=100`;
            }
            
            // Fetch both current and forecasted events in parallel
            const [currentResponse, forecastedResponse] = await Promise.all([
                fetch(currentUrl),
                fetch(forecastedUrl).catch(e => ({ ok: false, error: e })) // Gracefully handle if forecasted endpoint fails
            ]);
            
            // Process current events
            if (!currentResponse.ok) {
                const errorData = await currentResponse.json();
                throw new Error(errorData.detail || `HTTP error! status: ${currentResponse.status}`);
            }
            const currentEventsData = await currentResponse.json();

            let filteredCurrentData = currentEventsData;
            if (selectedEventType) {
                filteredCurrentData = currentEventsData.filter(event => 
                    event.potential_event_types && event.potential_event_types.includes(selectedEventType)
                );
            }
            setDisplayedEvents(filteredCurrentData);
            
            // Process forecasted events
            let filteredForecastedData = [];
            if (forecastedResponse.ok) {
                const forecastedEventsData = await forecastedResponse.json();
                filteredForecastedData = forecastedEventsData;
                if (selectedEventType) {
                    filteredForecastedData = forecastedEventsData.filter(event => 
                        event.potential_event_types && event.potential_event_types.includes(selectedEventType)
                    );
                }
            } else {
                console.warn("Forecasted events endpoint not available or returned error");
            }
            setForecastedEvents(filteredForecastedData);
            
        } catch (e) {
            console.error("Error fetching events:", e);
            setError(`Failed to load event data: ${e.message}`);
        } finally {
            setLoading(false);
        }
    }, [selectedNode, selectedEventType]); // Dependencies for useCallback

    // Initial data load for suppliers and summary
    useEffect(() => {
        const fetchInitialData = async () => {
            setError(null); // Clear previous errors
            try {
                const [suppliersRes, summaryRes] = await Promise.all([
                    fetch(`${API_BASE_URL}/suppliers`),
                    fetch(`${API_BASE_URL}/summary`)
                ]);

                if (!suppliersRes.ok) throw new Error(`Failed to fetch suppliers: ${suppliersRes.status}`);
                if (!summaryRes.ok) {
                    const errorData = await summaryRes.json();
                    throw new Error(errorData.detail || `Failed to fetch summary: ${summaryRes.status}`);
                }

                setSuppliers(await suppliersRes.json());
                setSummary(await summaryRes.json());
            } catch (e) {
                console.error("Error fetching initial data:", e);
                setError(`Failed to load initial data: ${e.message}`);
            }
        };
        fetchInitialData();
    }, []); // Empty dependency array means this runs once on mount

    // Effect to fetch events when filters change
    useEffect(() => {
        fetchEvents();
    }, [fetchEvents]); // fetchEvents is a dependency

    const handleResetFilters = () => {
        setSelectedNode('');
        setSelectedEventType('');
    };
    
    // --- UI Rendering ---
    if (error && !summary && !loading) { // Show critical error if initial load fails and not just loading
        return (
            <div className="dashboard-header" style={{ color: 'red', textAlign: 'center', padding: '20px' }}>
                <h2>Application Error</h2>
                <p>{error}</p>
                <p>Please check your backend server and database connection.</p>
            </div>
        );
    }

    return (
        <>
            <div className="dashboard-header">
                <h1>Supply Chain Disruption Forecaster</h1>
                {summary ? (
                    <div className="summary-stats">
                        <span>Total Events Logged: <strong>{summary.total_events}</strong></span> |
                        <span>Avg. Base Risk Score: <strong>{summary.avg_risk_score ? summary.avg_risk_score.toFixed(2) : 'N/A'}</strong></span> |
                        <span>Most Common Event: <strong>{summary.most_common_event_type ? summary.most_common_event_type.replace(/_/g, ' ') : 'N/A'}</strong></span>
                    </div>
                ) : (
                    <p>Loading summary data...</p>
                )}
            </div>
            <div className="main-content">
                <div className="sidebar">
                    <div className="filters-container">
                        <h2>Filters</h2>
                        <div className="filter-group">
                            <label htmlFor="node-select">Supplier Node</label>
                            <select id="node-select" value={selectedNode} onChange={(e) => setSelectedNode(e.target.value)}>
                                <option value="">All Nodes</option>
                                {suppliers.map(s => <option key={s.id} value={s.node_name}>{s.node_name}</option>)}
                            </select>
                        </div>
                        <div className="filter-group">
                            <label htmlFor="event-type-select">Event Type</label>
                            <select id="event-type-select" value={selectedEventType} onChange={(e) => setSelectedEventType(e.target.value)}>
                                <option value="">All Event Types</option>
                                {EVENT_TYPES.map(type => <option key={type} value={type}>{type.replace(/_/g, ' ')}</option>)}
                            </select>
                        </div>
                        <div className="filter-group">
                            <label style={{display: 'flex', alignItems: 'center', cursor: 'pointer'}}>
                                <input 
                                    type="checkbox" 
                                    checked={showCurrentEvents} 
                                    onChange={(e) => setShowCurrentEvents(e.target.checked)}
                                    style={{marginRight: '8px'}}
                                />
                                Show Current Events
                            </label>
                        </div>
                        <div className="filter-group">
                            <label style={{display: 'flex', alignItems: 'center', cursor: 'pointer'}}>
                                <input 
                                    type="checkbox" 
                                    checked={showForecastedEvents} 
                                    onChange={(e) => setShowForecastedEvents(e.target.checked)}
                                    style={{marginRight: '8px'}}
                                />
                                Show Forecasted Events 🔮
                            </label>
                        </div>
                        <div className="filter-group">
                            <button onClick={handleResetFilters}>Reset Filters</button>
                        </div>
                    </div>

                    {selectedNode && (
                        <div className="forecast-container" style={{ padding: '15px', borderBottom: '1px solid #e0e0e0', minHeight: '300px' }}>
                            <h2>Risk Forecast</h2>
                            <ForecastChart nodeName={selectedNode} />
                        </div>
                    )}

                    <div className="event-list-container">
                        <h2>{selectedNode ? `Events for ${selectedNode}` : 'All Events'}</h2>
                        {loading ? <p>Loading events...</p> : (
                            <>
                                {/* Current Events Section */}
                                {showCurrentEvents && (
                                    <div style={{marginBottom: '20px'}}>
                                        <h3 style={{fontSize: '1.1em', borderBottom: '2px solid #e74c3c', paddingBottom: '5px'}}>
                                            Current Events ({displayedEvents.length})
                                        </h3>
                                        <ul className="event-list">
                                            {displayedEvents.length === 0 && <p>No current events found.</p>}
                                            {displayedEvents.map(event => (
                                                <li key={`current-${event.id}`} className={`event-item ${getImpactClass(event.impact_score)}`}>
                                                    <h4>{event.article_title || 'No Title'}</h4>
                                                    <p>Node: <strong>{event.matched_node || 'N/A'}</strong></p>
                                                    <p>Impact: <strong className="impact-score-display">{event.impact_score ? event.impact_score.toFixed(1) : 'N/A'}</strong></p>
                                                    <p>Base Risk: {event.risk_score ? event.risk_score.toFixed(1) : 'N/A'}</p>
                                                    <p>Type(s): {event.potential_event_types && event.potential_event_types.length > 0 ? event.potential_event_types.join(', ').replace(/_/g, ' ') : 'N/A'}</p>
                                                    <p>Date: {event.article_timestamp ? new Date(event.article_timestamp).toLocaleDateString() : 'N/A'}</p>
                                                    {event.article_url && <a href={event.article_url} target="_blank" rel="noopener noreferrer" className="source-link">Source</a>}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {/* Forecasted Events Section */}
                                {showForecastedEvents && (
                                    <div>
                                        <h3 style={{fontSize: '1.1em', borderBottom: '2px solid #3498db', paddingBottom: '5px'}}>
                                            🔮 Forecasted Events ({forecastedEvents.length})
                                        </h3>
                                        <ul className="event-list">
                                            {forecastedEvents.length === 0 && <p style={{fontStyle: 'italic', color: '#666'}}>
                                                No forecasted events. Run temporal extraction to detect predicted events.
                                            </p>}
                                            {forecastedEvents.map(event => (
                                                <li key={`forecasted-${event.id}`} className={`event-item forecasted-event-item ${getImpactClass(event.impact_score)}`}>
                                                    <h4>🔮 {event.article_title || 'No Title'}</h4>
                                                    <p>Node: <strong>{event.matched_node || 'N/A'}</strong></p>
                                                    <p>Impact: <strong className="impact-score-display">{event.impact_score ? event.impact_score.toFixed(1) : 'N/A'}</strong></p>
                                                    {event.temporal_info && (
                                                        <>
                                                            <p style={{color: '#3498db', fontWeight: 'bold'}}>
                                                                Predicted Date: {event.temporal_info.predicted_date ? 
                                                                    new Date(event.temporal_info.predicted_date).toLocaleDateString() : 'Unknown'}
                                                            </p>
                                                            <p style={{fontSize: '0.9em'}}>
                                                                Confidence: <span style={{
                                                                    padding: '2px 8px', 
                                                                    borderRadius: '3px',
                                                                    backgroundColor: event.temporal_info.predicted_date_confidence === 'high' ? '#27ae60' :
                                                                                    event.temporal_info.predicted_date_confidence === 'medium' ? '#f39c12' : '#95a5a6',
                                                                    color: 'white',
                                                                    fontSize: '0.85em'
                                                                }}>
                                                                    {event.temporal_info.predicted_date_confidence || 'unknown'}
                                                                </span>
                                                            </p>
                                                            {event.temporal_info.days_until_event !== null && (
                                                                <p style={{fontSize: '0.9em', color: '#e67e22'}}>
                                                                    ⏱️ {event.temporal_info.days_until_event} days until event
                                                                </p>
                                                            )}
                                                        </>
                                                    )}
                                                    <p>Type(s): {event.potential_event_types && event.potential_event_types.length > 0 ? event.potential_event_types.join(', ').replace(/_/g, ' ') : 'N/A'}</p>
                                                    {event.article_url && <a href={event.article_url} target="_blank" rel="noopener noreferrer" className="source-link">Source</a>}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </div>
                <div className="map-wrapper">
                    {/* Map Legend */}
                    <div style={{
                        position: 'absolute',
                        top: '10px',
                        right: '10px',
                        backgroundColor: 'white',
                        padding: '10px',
                        borderRadius: '5px',
                        boxShadow: '0 2px 5px rgba(0,0,0,0.2)',
                        zIndex: 1000,
                        fontSize: '0.85em'
                    }}>
                        <h4 style={{margin: '0 0 10px 0', fontSize: '1em'}}>Legend</h4>
                        <div style={{marginBottom: '5px'}}><span style={{fontSize: '1.2em'}}>🏭</span> Supplier Nodes</div>
                        <div style={{marginBottom: '5px'}}><span style={{fontSize: '1.2em'}}>🚨</span> Current Events</div>
                        <div style={{marginBottom: '5px'}}><span style={{fontSize: '1.2em'}}>🔮</span> Forecasted Events</div>
                        <div style={{fontSize: '0.8em', marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #ddd'}}>
                            <div>Forecasted = predicted future events</div>
                            <div style={{color: '#27ae60'}}>● High confidence</div>
                            <div style={{color: '#f39c12'}}>● Medium confidence</div>
                            <div style={{color: '#95a5a6'}}>● Low confidence</div>
                        </div>
                    </div>

                    <MapContainer center={MAP_CENTER} zoom={MAP_ZOOM} className="leaflet-container">
                        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors' />
                        
                        {/* Supplier Markers */}
                        {suppliers.map(supplier => (
                            <Marker key={`supplier-${supplier.id}`} position={[supplier.latitude, supplier.longitude]} icon={getSupplierIcon(supplier.criticality)}>
                                <Popup>
                                    <h3>{supplier.node_name}</h3>
                                    <p>Country: {supplier.country}</p>
                                    <p>Criticality: {supplier.criticality}</p>
                                    <button onClick={() => setSelectedNode(supplier.node_name)}>View Events</button>
                                </Popup>
                                <Tooltip>{supplier.node_name} (Criticality: {supplier.criticality})</Tooltip>
                            </Marker>
                        ))}

                        {/* Current Event Markers */}
                        {showCurrentEvents && displayedEvents.map(event => event.latitude && event.longitude && (
                            <Marker key={`event-${event.id}`} position={[event.latitude, event.longitude]} icon={getEventImpactIcon(event.impact_score)}>
                                <Popup>
                                    <h3>Current Event</h3>
                                    <h4>{event.article_title || 'No Title'}</h4>
                                    <p><strong>Node:</strong> {event.matched_node || 'N/A'}</p>
                                    <p><strong>Impact Score:</strong> <span className={`impact-score-popup ${getImpactClass(event.impact_score)}`}>{event.impact_score ? event.impact_score.toFixed(1) : 'N/A'}</span></p>
                                    <p><strong>Base Risk Score:</strong> {event.risk_score ? event.risk_score.toFixed(1) : 'N/A'}</p>
                                    <p><strong>Type(s):</strong> {event.potential_event_types && event.potential_event_types.length > 0 ? event.potential_event_types.join(', ').replace(/_/g, ' ') : 'N/A'}</p>
                                    <p><strong>Date:</strong> {event.article_timestamp ? new Date(event.article_timestamp).toLocaleDateString() : 'N/A'}</p>
                                    {event.article_url && <a href={event.article_url} target="_blank" rel="noopener noreferrer">Read more</a>}
                                </Popup>
                                <Tooltip>{event.matched_node || 'Event'} - Impact: {event.impact_score ? event.impact_score.toFixed(1) : 'N/A'}</Tooltip>
                            </Marker>
                        ))}

                        {/* Forecasted Event Markers */}
                        {showForecastedEvents && forecastedEvents.map(event => event.latitude && event.longitude && (
                            <Marker 
                                key={`forecasted-${event.id}`} 
                                position={[event.latitude, event.longitude]} 
                                icon={getForecastedEventIcon(
                                    event.impact_score, 
                                    event.temporal_info?.predicted_date_confidence
                                )}
                            >
                                <Popup>
                                    <h3 style={{color: '#3498db'}}>🔮 Forecasted Event</h3>
                                    <h4>{event.article_title || 'No Title'}</h4>
                                    <p><strong>Node:</strong> {event.matched_node || 'N/A'}</p>
                                    <p><strong>Impact Score:</strong> <span className={`impact-score-popup ${getImpactClass(event.impact_score)}`}>{event.impact_score ? event.impact_score.toFixed(1) : 'N/A'}</span></p>
                                    {event.temporal_info && (
                                        <>
                                            <p style={{color: '#3498db', fontWeight: 'bold'}}>
                                                <strong>Predicted Date:</strong> {event.temporal_info.predicted_date ? 
                                                    new Date(event.temporal_info.predicted_date).toLocaleDateString() : 'Unknown'}
                                            </p>
                                            <p>
                                                <strong>Confidence:</strong> <span style={{
                                                    padding: '2px 6px',
                                                    borderRadius: '3px',
                                                    backgroundColor: event.temporal_info.predicted_date_confidence === 'high' ? '#27ae60' :
                                                                    event.temporal_info.predicted_date_confidence === 'medium' ? '#f39c12' : '#95a5a6',
                                                    color: 'white',
                                                    fontSize: '0.85em'
                                                }}>
                                                    {event.temporal_info.predicted_date_confidence || 'unknown'}
                                                </span>
                                            </p>
                                            {event.temporal_info.days_until_event !== null && (
                                                <p style={{color: '#e67e22'}}>
                                                    <strong>⏱️ Days Until:</strong> {event.temporal_info.days_until_event}
                                                </p>
                                            )}
                                            <p><strong>Time Horizon:</strong> {event.temporal_info.time_horizon || 'unknown'}</p>
                                        </>
                                    )}
                                    <p><strong>Type(s):</strong> {event.potential_event_types && event.potential_event_types.length > 0 ? event.potential_event_types.join(', ').replace(/_/g, ' ') : 'N/A'}</p>
                                    {event.article_url && <a href={event.article_url} target="_blank" rel="noopener noreferrer">Read more</a>}
                                </Popup>
                                <Tooltip>
                                    🔮 {event.matched_node || 'Forecasted'} - 
                                    {event.temporal_info?.predicted_date ? 
                                        ` ${new Date(event.temporal_info.predicted_date).toLocaleDateString()}` : 
                                        ' Future Event'}
                                </Tooltip>
                            </Marker>
                        ))}
                    </MapContainer>
                </div>
            </div>
        </>
    );
}

export default App;