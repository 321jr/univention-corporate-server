package univention

import javaposse.jobdsl.dsl.jobs.*


class Jobs {

  def createAppAutotestUpdateMultiEnv(String path, String version, String patch_level, Map app) {
  
    def desc = 'App Autotest Update MultiEnv'
    def job_name = path + '/' + desc
  
    matrixJob(job_name) {
  
      authenticationToken('secret')
      
      // config
      quietPeriod(60)
      logRotator(-1, 5, -1, -1)
      description("run ${desc} for ${app.id}")
      concurrentBuild()
  
      // build parameters
      parameters {
        booleanParam('HALT', true, 'uncheck to disable shutdown of ec2 instances')
        booleanParam('Update_to_testing_errata_updates', false, 'Update to unreleased errata updates from updates-test.software-univention.de?')
      }
      
      // svn
      scm {
        svn {
          checkoutStrategy(SvnCheckoutStrategy.CHECKOUT)
          location("svn+ssh://svnsync@billy/var/svn/dev/branches/ucs-${version}/ucs-${version}-${patch_level}/test/ucs-ec2-tools") {
            credentials('50021505-442b-438a-8ceb-55ea76d905d3')    
          }
          configure { scmNode ->
            scmNode / browser(class: 'hudson.plugins.websvn2.WebSVN2RepositoryBrowser') {
              url('https://billy.knut.univention.de/websvn/listing.php/?repname=dev')
              baseUrl('https://billy.knut.univention.de/websvn/')
              repname('repname=dev')      
            }
          }
        }
      }
      
      // axies
      axes {
        text('Systemrolle', app.roles)
        text('SambaVersion', 's3', 's4')
      }
      
      // wrappers
      wrappers {
        preBuildCleanup()
      }
      
      // build step
      steps {
        cmd = """
  cfg="examples/jenkins/autotest-12*-appupdate-\${Systemrolle}-\${SambaVersion}.cfg"
  sed -i "s|APP_ID|${app.required_apps.join(' ')}|g" \$cfg
  test "\$Update_to_testing_errata_updates" = true && sed -i "s|upgrade_to_latest_errata|upgrade_to_latest_test_errata|g" \$cfg
  exec ./ucs-ec2-create -c \$cfg"""
        shell(cmd)
      }
      
      // post build
      publishers {
        archiveArtifacts('**/autotest-*.log,**/ucs-test.log,**/updater.log,**/setup.log,**/join.log,**/*.log')
        archiveJunit('**/test-reports/**/*.xml')
      }
    }
  }
}
