import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import ThemeRegistry from './ThemeRegistry';
import router from './router';

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeRegistry>
        <RouterProvider router={router} />
      </ThemeRegistry>
    </QueryClientProvider>
  );
}
