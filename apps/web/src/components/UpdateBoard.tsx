import { useQuery } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';

const API = 'http://localhost:8000';

interface Hazard {
  id: number;
  latitude: number;
  longitude: number;
  hazard_type: string;
  severity: number;
  description: string | null;
  source: string;
  created_at: string;
}

const severityColor: Record<number, 'success' | 'warning' | 'error'> = {
  1: 'success',
  2: 'success',
  3: 'warning',
  4: 'error',
  5: 'error',
};

const severityBorder: Record<number, string> = {
  1: '#00DD00',
  2: '#AAFF00',
  3: '#FFD600',
  4: '#FF6600',
  5: '#FF1744',
};

function timeAgo(dateStr: string) {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function UpdateBoard() {
  const { data: hazards = [] } = useQuery<Hazard[]>({
    queryKey: ['hazards'],
    queryFn: () =>
      fetch(`${API}/hazards?lat=41.88&lng=-87.63&radius_km=100`).then((r) => r.json()),
    refetchInterval: 5000,
  });

  const sorted = [...hazards].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, maxHeight: '75vh', overflow: 'auto' }}>
      {sorted.length === 0 && (
        <Card
          variant="outlined"
          sx={{
            borderRadius: '10px',
            border: '1px solid #333',
            bgcolor: '#111',
            textAlign: 'center',
            py: 4,
          }}
        >
          <CardContent>
            <Typography color="text.secondary" sx={{ fontSize: '1.1rem' }}>
              No hazards detected yet. Start a ride to see live events.
            </Typography>
          </CardContent>
        </Card>
      )}
      {sorted.map((hazard) => (
        <Card
          key={hazard.id}
          variant="outlined"
          sx={{
            borderRadius: '10px',
            border: '1px solid #333',
            borderLeft: `3px solid ${severityBorder[hazard.severity] ?? '#333'}`,
            bgcolor: '#111',
            transition: 'border-color 0.2s ease, background-color 0.2s ease',
            '&:hover': { bgcolor: '#1a1a1a', borderColor: '#555' },
          }}
        >
          <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, py: 1.5, '&:last-child': { pb: 1.5 } }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <Typography fontWeight={600} sx={{ textTransform: 'capitalize', fontSize: '0.95rem' }}>
                  {hazard.hazard_type.replace('_', ' ')}
                </Typography>
                <Chip
                  label={`Severity ${hazard.severity}`}
                  size="small"
                  color={severityColor[hazard.severity] ?? 'default'}
                  sx={{ fontWeight: 500, height: 22 }}
                />
              </Box>
              <Typography variant="caption" sx={{ color: '#666', fontWeight: 500 }}>
                {timeAgo(hazard.created_at)}
              </Typography>
            </Box>
            {hazard.description && (
              <Typography variant="body2" sx={{ color: '#aaa', mt: 0.5 }}>
                {hazard.description}
              </Typography>
            )}
            <Typography variant="caption" sx={{ color: '#555', fontFamily: 'monospace' }}>
              {hazard.latitude.toFixed(4)}, {hazard.longitude.toFixed(4)}
            </Typography>
          </CardContent>
        </Card>
      ))}
    </Box>
  );
}
