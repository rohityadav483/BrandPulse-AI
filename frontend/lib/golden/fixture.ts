import fixture from '../../../contracts/golden/samsung_battery.json';import type {components} from '@/lib/api/types.generated';
type DashboardResponse=components['schemas']['DashboardResponse'];type SignalDetail=components['schemas']['SignalDetail'];type InvestigationResponse=components['schemas']['InvestigationResponse'];type ListEvidenceResponse=components['schemas']['ListEvidenceResponse'];
export const goldenFixture=fixture as unknown as {dashboard:DashboardResponse;signal_detail:SignalDetail;investigation:InvestigationResponse;evidence:ListEvidenceResponse};
