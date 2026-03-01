import { Button } from '@mui/material';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import { Link } from 'react-router-dom';

export default function Header() {
  return (
    <AppBar position="sticky" sx={{ bgcolor: '#000', borderBottom: '1px solid #333' }}>
      <Toolbar>
        <Typography
          fontWeight="bold"
          variant="h6"
          component="div"
          sx={{ flexGrow: 0, mr: 4, color: '#00DD00' }}
        >
          ScootSafe
        </Typography>
        <div className="flex flex-row gap-2">
          <Link to="/">
            <Button sx={{ color: '#fff', '&:hover': { color: '#00DD00' } }}>Map Dashboard</Button>
          </Link>
          <Link to="/live">
            <Button sx={{ color: '#fff', '&:hover': { color: '#00DD00' } }}>Live Feed</Button>
          </Link>
          <Link to="/about">
            <Button sx={{ color: '#fff', '&:hover': { color: '#00DD00' } }}>About</Button>
          </Link>
        </div>
      </Toolbar>
    </AppBar>
  );
}
