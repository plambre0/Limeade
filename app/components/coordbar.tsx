import { CardContent, Typography } from "@mui/material";
import Card from '@mui/material/Card';

export default function Coordbar({ selected }: { selected: { lat: number; lng: number; label: string } | null }){
    return(
        <Card variant="outlined" sx={{ borderRadius: '10px', boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.1)',
            border: '2px solid #322332',
            transition: 'transform 0.2s ease',
            '&:hover': {
            transform: 'scale(1.05)',
            cursor: 'pointer',
            }
         }}>{
            <CardContent>
                <Typography component={"div"} gutterBottom variant="h5"> Event Coordinates</Typography>
                {selected ? (
                <>
                    <Typography>Lat: {selected.lat}</Typography>
                    <Typography>Lng: {selected.lng}</Typography>
                </>
                ) : (
                <Typography>Click a marker to see coordinates</Typography>
                )}
            </CardContent>
        }</Card>
    )
}