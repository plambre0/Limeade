import { createBrowserRouter } from 'react-router-dom';
import Layout from './Layout';
import Home from './Home';
import LivePage from './pages/LivePage';
import AboutPage from './pages/AboutPage';

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <Home /> },
      { path: '/live', element: <LivePage /> },
      { path: '/about', element: <AboutPage /> },
    ],
  },
]);

export default router;
