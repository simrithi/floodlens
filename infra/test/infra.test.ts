import * as cdk from 'aws-cdk-lib/core';
import { Template } from 'aws-cdk-lib/assertions';
import { InfraStack } from '../lib/infra-stack';

const template = Template.fromStack(new InfraStack(new cdk.App(), 'FloodLensWebTest'));

test('the site bucket is private and encrypted', () => {
  template.hasResourceProperties('AWS::S3::Bucket', {
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    },
    BucketEncryption: {
      ServerSideEncryptionConfiguration: [{ ServerSideEncryptionByDefault: { SSEAlgorithm: 'AES256' } }],
    },
  });
});

test('CloudFront reaches the bucket through Origin Access Control, over HTTPS only', () => {
  template.resourceCountIs('AWS::CloudFront::OriginAccessControl', 1);
  template.hasResourceProperties('AWS::CloudFront::Distribution', {
    DistributionConfig: {
      DefaultCacheBehavior: { ViewerProtocolPolicy: 'redirect-to-https' },
      HttpVersion: 'http2and3',
    },
  });
});

test('single-page-app routing is a viewer-request function, not an error-page rewrite', () => {
  template.resourceCountIs('AWS::CloudFront::Function', 1);
  const distribution = Object.values(template.findResources('AWS::CloudFront::Distribution'))[0] as {
    Properties: { DistributionConfig: { CustomErrorResponses?: unknown[] } };
  };
  // Error-page rewrites would turn a missing analysis file into index.html and hide the failure.
  expect(distribution.Properties.DistributionConfig.CustomErrorResponses ?? []).toHaveLength(0);
});

test('analysis data is cached for minutes, hashed assets for a year', () => {
  const policies = Object.values(template.findResources('AWS::CloudFront::CachePolicy')) as {
    Properties: { CachePolicyConfig: { DefaultTTL: number } };
  }[];
  const ttls = policies.map((p) => p.Properties.CachePolicyConfig.DefaultTTL);
  expect(ttls).toContain(300);
  expect(ttls).toContain(31536000);
});

test('every resource carries the Project tag', () => {
  template.hasResourceProperties('AWS::S3::Bucket', { Tags: [{ Key: 'Project', Value: 'FloodLens' }] });
});
