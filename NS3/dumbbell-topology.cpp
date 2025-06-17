#include <iostream>
#include <fstream>
#include <string>
#include <sstream>
#include <vector>
#include <cmath>
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "ns3/core-module.h"
#include "ns3/packet-sink.h"
#include "ns3/point-to-point-dumbbell.h"
#include "ns3/point-to-point-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/applications-module.h"
 
using namespace ns3;
using namespace std;
 
NS_LOG_COMPONENT_DEFINE("TcpExperimentSharan");
 
// Experiment data structure
struct ExperimentData {
  vector<double> throughputs;
  vector<double> flowTimes;
  double meanThroughput;
  double stddevThroughput;
  double meanFlowTime;
  double stddevFlowTime;
};
 
// Helper function to calculate statistics
void CalculateStats(vector<double> &values, double &mean, double &stddev)
{
  mean = 0.0;
  stddev = 0.0;
 
  if (values.empty())
    return;
 
  // Calculate mean
  for (const auto &val : values)
  {
    mean += val;
  }
  mean /= values.size();
 
  // Calculate standard deviation
  for (const auto &val : values)
  {
    stddev += pow(val - mean, 2);
  }
  stddev = sqrt(stddev / values.size());
}
 
// Initialize TCP configurations
void SetupTcpConfig()
{
  Config::SetDefault("ns3::TcpSocket::RcvBufSize", UintegerValue(1073741824));
  Config::SetDefault("ns3::TcpSocket::SndBufSize", UintegerValue(1073741824));
  Config::SetDefault("ns3::TcpSocket::SegmentSize", UintegerValue(1448));
  Config::SetDefault("ns3::TcpSocketBase::WindowScaling", BooleanValue(true));
  Config::SetDefault("ns3::TcpSocketBase::MinRto", TimeValue(MilliSeconds(5)));
}
 
// Setup dumbbell topology
PointToPointDumbbellHelper SetupDumbbell(const string &tcpVariant, string prefix)
{
  Config::SetDefault("ns3::TcpL4Protocol::SocketType", StringValue("ns3::" + tcpVariant));
  
  PointToPointHelper leftLinks, rightLinks, bottleneckLink;
  leftLinks.SetDeviceAttribute("DataRate", StringValue("1Gbps"));
  rightLinks.SetDeviceAttribute("DataRate", StringValue("1Gbps"));
  bottleneckLink.SetDeviceAttribute("DataRate", StringValue("1Gbps"));
 
  PointToPointDumbbellHelper dumbbell(2, leftLinks, 2, rightLinks, bottleneckLink);
  
  InternetStackHelper internetStack;
  dumbbell.InstallStack(internetStack);
 
  // Assign IP addresses
  Ipv4AddressHelper leftIPs, rightIPs, centerIPs;
  leftIPs.SetBase((prefix + ".1.0").c_str(), "255.255.255.252");
  rightIPs.SetBase((prefix + ".2.0").c_str(), "255.255.255.252");
  centerIPs.SetBase((prefix + ".3.0").c_str(), "255.255.255.252");
 
  dumbbell.AssignIpv4Addresses(leftIPs, rightIPs, centerIPs);
  
  return dumbbell;
}
 
// Create mixed dumbbell with different TCP variants
PointToPointDumbbellHelper SetupMixedDumbbell(string prefix)
{
  PointToPointHelper leftLinks, rightLinks, bottleneckLink;
  leftLinks.SetDeviceAttribute("DataRate", StringValue("1Gbps"));
  rightLinks.SetDeviceAttribute("DataRate", StringValue("1Gbps"));
  bottleneckLink.SetDeviceAttribute("DataRate", StringValue("1Gbps"));
 
  PointToPointDumbbellHelper dumbbell(2, leftLinks, 2, rightLinks, bottleneckLink);
 
  // Install different TCP variants on different nodes
  Config::SetDefault("ns3::TcpL4Protocol::SocketType", StringValue("ns3::TcpBic"));
  InternetStackHelper stackBic;
  stackBic.Install(dumbbell.GetLeft(0));
  stackBic.Install(dumbbell.GetRight(0));
 
  Config::SetDefault("ns3::TcpL4Protocol::SocketType", StringValue("ns3::TcpDctcp"));
  InternetStackHelper stackDctcp;
  stackDctcp.Install(dumbbell.GetLeft(1));
  stackDctcp.Install(dumbbell.GetRight(1));
 
  stackDctcp.Install(dumbbell.GetLeft());
  stackDctcp.Install(dumbbell.GetRight());
 
  // Assign IP addresses
  Ipv4AddressHelper leftIPs, rightIPs, centerIPs;
  leftIPs.SetBase((prefix + ".1.0").c_str(), "255.255.255.252");
  rightIPs.SetBase((prefix + ".2.0").c_str(), "255.255.255.252");
  centerIPs.SetBase((prefix + ".3.0").c_str(), "255.255.255.252");
 
  dumbbell.AssignIpv4Addresses(leftIPs, rightIPs, centerIPs);
 
  return dumbbell;
}
 
// Setup a sender-receiver experiment
void SetupExperiment(
    PointToPointDumbbellHelper &dumbbell,
    uint16_t port,
    uint32_t maxBytes,
    double startTime,
    double endTime,
    bool twoSenders = false)
{
  // Create packet sinks
  PacketSinkHelper sinkHelper("ns3::TcpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), port));
  
  ApplicationContainer sink1 = sinkHelper.Install(dumbbell.GetRight(0));
  sink1.Start(Seconds(startTime));
  sink1.Stop(Seconds(endTime));
 
  if (twoSenders) {
    ApplicationContainer sink2 = sinkHelper.Install(dumbbell.GetRight(1));
    sink2.Start(Seconds(startTime));
    sink2.Stop(Seconds(endTime));
  }
 
  // Create senders
  BulkSendHelper sender1("ns3::TcpSocketFactory", InetSocketAddress(dumbbell.GetRightIpv4Address(0), port));
  sender1.SetAttribute("MaxBytes", UintegerValue(maxBytes));
  
  // Three runs for first sender
  for (int run = 0; run < 3; run++) {
    double runStart = startTime + run * 10;
    double runEnd = runStart + 10;
    
    ApplicationContainer app1 = sender1.Install(dumbbell.GetLeft(0));
    app1.Start(Seconds(runStart));
    app1.Stop(Seconds(runEnd));
  }
 
  // If two senders, setup the second sender
  if (twoSenders) {
    BulkSendHelper sender2("ns3::TcpSocketFactory", InetSocketAddress(dumbbell.GetRightIpv4Address(1), port));
    sender2.SetAttribute("MaxBytes", UintegerValue(maxBytes));
    
    // Three runs for second sender
    for (int run = 0; run < 3; run++) {
      double runStart = startTime + run * 10;
      double runEnd = runStart + 10;
      
      ApplicationContainer app2 = sender2.Install(dumbbell.GetLeft(1));
      app2.Start(Seconds(runStart));
      app2.Stop(Seconds(runEnd));
    }
  }
}
 
// Process flow monitor results to extract experiment data
void ProcessFlowMonitorResults(
    Ptr<FlowMonitor> flowMonitor,
    Ptr<Ipv4FlowClassifier> classifier,
    vector<PointToPointDumbbellHelper> &dumbbells,
    vector<pair<double, double>> &expTimings,
    vector<ExperimentData> &expData)
{
  std::map<FlowId, FlowMonitor::FlowStats> stats = flowMonitor->GetFlowStats();
 
  // Process each flow
  for (auto it = stats.begin(); it != stats.end(); ++it) {
    Ipv4FlowClassifier::FiveTuple tuple = classifier->FindFlow(it->first);
    
    // Only process significant flows (not ACKs)
    if (it->second.rxBytes > 1000000) {
      double tputMbps = (it->second.rxBytes * 8.0) /
                        (it->second.timeLastRxPacket.GetSeconds() - it->second.timeFirstTxPacket.GetSeconds()) / 1e6;
      double fct = it->second.timeLastTxPacket.GetSeconds() - it->second.timeFirstTxPacket.GetSeconds();
      double startTime = it->second.timeFirstTxPacket.GetSeconds();
      
      // Determine which experiment this flow belongs to
      for (size_t expIdx = 0; expIdx < expTimings.size(); expIdx++) {
        double expStart = expTimings[expIdx].first;
        double expEnd = expTimings[expIdx].second;
        
        if (startTime >= expStart && startTime < expEnd) {
          // First dumbbell - experiments 0 and 1
          if (expIdx <= 1) {
            if (expIdx == 0 || tuple.sourceAddress == dumbbells[0].GetLeftIpv4Address(0)) {
              expData[expIdx * 2].throughputs.push_back(tputMbps);
              expData[expIdx * 2].flowTimes.push_back(fct);
            } else if (expIdx == 1 && tuple.sourceAddress == dumbbells[0].GetLeftIpv4Address(1)) {
              expData[expIdx * 2 + 1].throughputs.push_back(tputMbps);
              expData[expIdx * 2 + 1].flowTimes.push_back(fct);
            }
          }
          // Second dumbbell - experiments 2 and 3
          else if (expIdx <= 3) {
            if (expIdx == 2 || tuple.sourceAddress == dumbbells[1].GetLeftIpv4Address(0)) {
              expData[expIdx * 2].throughputs.push_back(tputMbps);
              expData[expIdx * 2].flowTimes.push_back(fct);
            } else if (expIdx == 3 && tuple.sourceAddress == dumbbells[1].GetLeftIpv4Address(1)) {
              expData[expIdx * 2 + 1].throughputs.push_back(tputMbps);
              expData[expIdx * 2 + 1].flowTimes.push_back(fct);
            }
          }
          // Third dumbbell - experiment 4
          else if (expIdx == 4) {
            if (tuple.sourceAddress == dumbbells[2].GetLeftIpv4Address(0)) {
              expData[expIdx * 2].throughputs.push_back(tputMbps);
              expData[expIdx * 2].flowTimes.push_back(fct);
            } else if (tuple.sourceAddress == dumbbells[2].GetLeftIpv4Address(1)) {
              expData[expIdx * 2 + 1].throughputs.push_back(tputMbps);
              expData[expIdx * 2 + 1].flowTimes.push_back(fct);
            }
          }
          break;
        }
      }
    }
  }
 
  // Calculate statistics for collected data
  for (auto &data : expData) {
    CalculateStats(data.throughputs, data.meanThroughput, data.stddevThroughput);
    CalculateStats(data.flowTimes, data.meanFlowTime, data.stddevFlowTime);
  }
}
 
// Write results to CSV file
void WriteResultsCsv(const string &filename, vector<ExperimentData> &expData) {
  ofstream csvFile;
  csvFile.open(filename);
  
  // Write header
  csvFile << "exp,r1_s1,r2_s1,r3_s1,avg_s1,std_s1,unit_s1,r1_s2,r2_s2,r3_s2,avg_s2,std_s2,unit_s2" << endl;
 
  // Write throughput data for each experiment
  for (int exp = 0; exp < 5; exp++) {
    csvFile << "th_" << (exp + 1) << ",";
    
    int firstFlowIdx = exp * 2;
    int secondFlowIdx = exp * 2 + 1;
    
    // First flow throughput
    for (int i = 0; i < min(3, (int)expData[firstFlowIdx].throughputs.size()); i++) {
      csvFile << expData[firstFlowIdx].throughputs[i] << ",";
    }
    
    csvFile << expData[firstFlowIdx].meanThroughput << "," 
            << expData[firstFlowIdx].stddevThroughput << ",Mbps,";
    
    // For single-flow experiments, add extra comma at the end
    if (exp == 0 || exp == 2) {
      csvFile << endl;
    } else {
      // Second flow throughput
      for (int i = 0; i < min(3, (int)expData[secondFlowIdx].throughputs.size()); i++) {
        csvFile << expData[secondFlowIdx].throughputs[i] << ",";
      }
      
      csvFile << expData[secondFlowIdx].meanThroughput << "," 
              << expData[secondFlowIdx].stddevThroughput << ",Mbps" << endl;
    }
  }
  
  // Write flow completion time data for each experiment
  for (int exp = 0; exp < 5; exp++) {
    csvFile << "afct_" << (exp + 1) << ",";
    
    int firstFlowIdx = exp * 2;
    int secondFlowIdx = exp * 2 + 1;
    
    // First flow FCT
    for (int i = 0; i < min(3, (int)expData[firstFlowIdx].flowTimes.size()); i++) {
      csvFile << expData[firstFlowIdx].flowTimes[i] << ",";
    }
    
    csvFile << expData[firstFlowIdx].meanFlowTime << "," 
            << expData[firstFlowIdx].stddevFlowTime << ",sec";
    
    // For single-flow experiments, add extra comma at the end
    if (exp == 0 || exp == 2) {
      csvFile << endl;
    } else {
      csvFile << ",";
      // Second flow FCT
      for (int i = 0; i < min(3, (int)expData[secondFlowIdx].flowTimes.size()); i++) {
        csvFile << expData[secondFlowIdx].flowTimes[i] << ",";
      }
      
      csvFile << expData[secondFlowIdx].meanFlowTime << "," 
              << expData[secondFlowIdx].stddevFlowTime << ",sec" << endl;
    }
  }
  
  csvFile.close();
}
 
int main(int argc, char *argv[])
{
  CommandLine cmd;
  cmd.Parse(argc, argv);
 
  // Initialize TCP configurations
  SetupTcpConfig();
 
  // Common experiment parameters
  uint32_t maxBytes = 50 * 1024 * 1024; // 50 MB
  Time simulationTime = Seconds(180.0);
  double timeOffset = 1.0; // Time between experiment segments
 
  // Vector to hold experiment start and end times
  vector<pair<double, double>> expTimings;
  
  // Initialize experiment timings
  double expStart = timeOffset;
  for (int i = 0; i < 5; i++) {
    double expEnd = expStart + 30;
    expTimings.push_back(make_pair(expStart, expEnd));
    expStart = expEnd + 1;
  }
 
  // Setup dumbbells for different experiments
  vector<PointToPointDumbbellHelper> dumbbells;
  
  // First dumbbell: TCPBic for experiments 1 & 2
  NS_LOG_INFO("Configuring dumbbell topology for TCPBic (Experiments 1 & 2)");
  dumbbells.push_back(SetupDumbbell("TcpBic", "10.1"));
  
  // Second dumbbell: DCTCP for experiments 3 & 4
  NS_LOG_INFO("Configuring dumbbell topology for DCTCP (Experiments 3 & 4)");
  dumbbells.push_back(SetupDumbbell("TcpDctcp", "10.2"));
  
  // Third dumbbell: Mixed TCP for experiment 5
  NS_LOG_INFO("Configuring dumbbell topology for Mixed TCP (Experiment 5)");
  dumbbells.push_back(SetupMixedDumbbell("10.3"));
 
  // Update routing tables
  Ipv4GlobalRoutingHelper::PopulateRoutingTables();
 
  // Setup experiments
  // Exp 1: Single flow with TCPBic
  SetupExperiment(dumbbells[0], 9001, maxBytes, expTimings[0].first, expTimings[0].second, false);
  
  // Exp 2: Two flows with TCPBic
  SetupExperiment(dumbbells[0], 9001, maxBytes, expTimings[1].first, expTimings[1].second, true);
  
  // Exp 3: Single flow with DCTCP
  SetupExperiment(dumbbells[1], 9002, maxBytes, expTimings[2].first, expTimings[2].second, false);
  
  // Exp 4: Two flows with DCTCP
  SetupExperiment(dumbbells[1], 9002, maxBytes, expTimings[3].first, expTimings[3].second, true);
  
  // Exp 5: One flow with TCPBic, one flow with DCTCP
  SetupExperiment(dumbbells[2], 9003, maxBytes, expTimings[4].first, expTimings[4].second, true);
 
  // Install flow monitor
  FlowMonitorHelper flowMonitorHelper;
  Ptr<FlowMonitor> flowMonitor = flowMonitorHelper.InstallAll();
  Ptr<Ipv4FlowClassifier> classifier = DynamicCast<Ipv4FlowClassifier>(flowMonitorHelper.GetClassifier());
 
  // Run simulation
  NS_LOG_INFO("Starting simulation...");
  Simulator::Stop(simulationTime);
  Simulator::Run();
 
  // Initialize experiment data structure (10 flows max: 2 per experiment)
  vector<ExperimentData> experimentData(10);
 
  // Process flow monitor results
  ProcessFlowMonitorResults(flowMonitor, classifier, dumbbells, expTimings, experimentData);
 
  // Write results to CSV
  WriteResultsCsv("tcp_srjamana.csv", experimentData);
 
  // Clean up
  Simulator::Destroy();
 
  cout << "Simulation completed. Results written to tcp_Sharan.csv" << endl;
  return 0;
}
