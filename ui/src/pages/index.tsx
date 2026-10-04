import type { ReactElement } from 'react';

import { AppLayout } from '@/core/layouts/app-layout';
import HomePage from '@/core/page-components/home/home';
import type { NextPageWithLayout } from '@/core/types/page';

const AgentsPage: NextPageWithLayout = () => {
  return <HomePage />;
};

// Attach layout to page
AgentsPage.getLayout = (page: ReactElement) => {
  return <AppLayout>{page}</AppLayout>;
};

export default AgentsPage;
